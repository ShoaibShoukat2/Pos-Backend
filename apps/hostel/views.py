from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.hostel.access import actor_context, ensure_perm, permission_codes
from apps.hostel.models import (
    HostelAuditLog,
    HostelBed,
    HostelBranch,
    HostelCustomer,
    HostelDocument,
    HostelEmployee,
    HostelExpense,
    HostelMaintenance,
    HostelMonthlyRent,
    HostelNotification,
    HostelPayment,
    HostelReservation,
    HostelRoom,
)
from apps.hostel.serializers import (
    AuditSerializer,
    BedSerializer,
    BranchSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerWriteSerializer,
    DocumentDetailSerializer,
    DocumentSerializer,
    EmployeeSerializer,
    ExpenseSerializer,
    MaintenanceSerializer,
    MonthlySerializer,
    NotificationSerializer,
    PaymentDetailSerializer,
    PaymentSerializer,
    ReservationSerializer,
    RoomSerializer,
    SettingsSerializer,
)
from apps.hostel.services import (
    accept_invite,
    adjust_bill,
    apply_late_fees,
    assign_permissions,
    build_report,
    cancel_reservation,
    change_room,
    check_in,
    check_out,
    clean_images,
    create_employee,
    create_reservation,
    dashboard,
    extend_stay,
    generate_months,
    guard_delete_branch,
    record_payment,
    refresh_overdue,
    require_branch,
    search_hostel,
    set_bed_status,
    settings_for,
    store_identity_docs,
    sync_room_beds,
    void_payment,
    open_beds,
)


def parse_date(value, field):
    if not value:
        raise ValidationError({field: "Choose a date."})
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValidationError({field: "Use a valid date."}) from exc


class HostelBase(BusinessQuerysetMixin):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.actor = actor_context(request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        names = {field.name for field in qs.model._meta.fields}
        if "is_deleted" in names:
            qs = qs.filter(is_deleted=False)
        if self.actor["role"] != "owner" and "branch" in names:
            qs = qs.filter(branch_id=self.actor["branch_id"])
        branch = self.request.query_params.get("branch")
        if branch and self.actor["role"] == "owner" and "branch" in names:
            qs = qs.filter(branch_id=branch)
        return qs

    def require(self, code):
        ensure_perm(self.actor, code)


def branch_counts(qs):
    return qs.annotate(
        total_rooms=Count("rooms", filter=Q(rooms__is_deleted=False), distinct=True),
        total_seats=Count("beds", filter=Q(beds__room__is_deleted=False), distinct=True),
        available_seats=Count("beds", filter=Q(beds__room__is_deleted=False, beds__status=HostelBed.Status.AVAILABLE), distinct=True),
        occupied_seats=Count("beds", filter=Q(beds__room__is_deleted=False, beds__status=HostelBed.Status.OCCUPIED), distinct=True),
        reserved_seats=Count("beds", filter=Q(beds__room__is_deleted=False, beds__status=HostelBed.Status.RESERVED), distinct=True),
    )


class BranchViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    queryset = HostelBranch.objects.all()
    pagination_class = None
    search_fields = ("name", "code", "city", "phone")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = branch_counts(super().get_queryset())
        if self.actor["role"] != "owner":
            qs = qs.filter(pk=self.actor["branch_id"])
        return qs

    def perform_create(self, serializer):
        self.require("branches.manage")
        serializer.save(business=self.request.user.business)

    def perform_update(self, serializer):
        self.require("branches.manage")
        serializer.save()

    def perform_destroy(self, instance):
        self.require("branches.manage")
        guard_delete_branch(instance)
        instance.delete()


class RoomViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    queryset = HostelRoom.objects.all()
    pagination_class = None
    search_fields = ("number", "facilities")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch").prefetch_related("beds__reservations__customer")
        floor = self.request.query_params.get("floor")
        if floor:
            qs = qs.filter(floor=floor)
        room_status = self.request.query_params.get("status")
        if room_status:
            qs = qs.filter(status=room_status)
        return qs

    def perform_create(self, serializer):
        self.require("rooms.manage")
        branch = require_branch(self.actor, serializer.validated_data["branch"])
        room = serializer.save(business=self.request.user.business, branch=branch)
        sync_room_beds(room)

    def perform_update(self, serializer):
        self.require("rooms.manage")
        if "branch" in serializer.validated_data:
            require_branch(self.actor, serializer.validated_data["branch"])
        room = serializer.save()
        sync_room_beds(room)

    def perform_destroy(self, instance):
        self.require("rooms.manage")
        if instance.beds.filter(reservations__status__in=["pending", "confirmed", "checked_in"]).exists():
            raise ValidationError({"detail": "This room has an open booking. Close it before removing the room."})
        instance.number = f"{instance.number}-{str(instance.pk)[:6]}"
        instance.is_deleted = True
        instance.status = HostelRoom.Status.INACTIVE
        instance.save(update_fields=["number", "is_deleted", "status", "updated_at"])


class BedViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = BedSerializer
    queryset = HostelBed.objects.all()
    pagination_class = None
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("room", "branch").prefetch_related("reservations__customer")
        qs = qs.filter(room__is_deleted=False)
        room = self.request.query_params.get("room")
        floor = self.request.query_params.get("floor")
        seat_status = self.request.query_params.get("status")
        if room:
            qs = qs.filter(room_id=room)
        if floor:
            qs = qs.filter(room__floor=floor)
        if seat_status:
            qs = qs.filter(status=seat_status)
        return qs

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "Seats are created with the room."})

    @action(detail=False, methods=["get"], url_path="open")
    def open(self, request):
        beds = open_beds(
            self.actor,
            branch_id=request.query_params.get("branch"),
            room_id=request.query_params.get("room"),
            floor=request.query_params.get("floor"),
            check_in=parse_date(request.query_params.get("check_in"), "check_in"),
            check_out=parse_date(request.query_params.get("check_out"), "check_out"),
        )
        return Response(BedSerializer(beds, many=True).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        bed = set_bed_status(self.actor, self.get_object(), request.data.get("status"))
        return Response(BedSerializer(bed).data)


class CustomerViewSet(HostelBase, viewsets.ModelViewSet):
    queryset = HostelCustomer.objects.all()
    search_fields = ("full_name", "father_name", "mobile", "whatsapp", "cnic", "room__number", "bed__code")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CustomerDetailSerializer
        if self.action in ("create", "partial_update"):
            return CustomerWriteSerializer
        return CustomerListSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "room", "bed")
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "monthly_rents", "payments", "documents", "reservations__customer",
                "reservations__room", "reservations__bed", "reservations__branch",
                "checkins__bed__room", "checkouts__bed__room",
            )
        else:
            qs = qs.prefetch_related("monthly_rents", "payments")
        customer_status = self.request.query_params.get("status")
        room = self.request.query_params.get("room")
        admission_from = self.request.query_params.get("admission_from")
        admission_to = self.request.query_params.get("admission_to")
        if customer_status:
            qs = qs.filter(status=customer_status)
        if room:
            qs = qs.filter(room_id=room)
        if admission_from:
            qs = qs.filter(admission_date__gte=admission_from)
        if admission_to:
            qs = qs.filter(admission_date__lte=admission_to)
        return qs

    def create(self, request, *args, **kwargs):
        self.require("customers.manage")
        serializer = CustomerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        bed_id = data.pop("bed_id", None)
        check_in_now = data.pop("check_in_now", False)
        branch = data.get("branch")
        if branch:
            require_branch(self.actor, branch)
        elif self.actor["role"] != "owner":
            data.pop("branch", None)
            data["branch"] = HostelBranch.objects.get(pk=self.actor["branch_id"])
        customer = HostelCustomer.objects.create(business=request.user.business, created_by=request.user, **data)
        store_identity_docs(customer, request.user)
        from apps.hostel.services import audit, notify
        audit(request.user.business, request.user, "customer.registered", customer.full_name, customer.branch, "customer", customer.pk)
        notify(request.user.business, "customer", "New customer", customer.full_name, f"/hostel/customers/{customer.pk}", customer.branch)
        if bed_id:
            bed = HostelBed.objects.select_related("room", "branch").get(pk=bed_id, business=request.user.business)
            reservation = create_reservation(
                self.actor,
                customer=customer,
                bed=bed,
                reservation_date=customer.admission_date or timezone.localdate(),
                check_in_date=customer.check_in_date or timezone.localdate(),
                expected_checkout=customer.expected_checkout or (timezone.localdate() + timedelta(days=30)),
                monthly_rent=customer.monthly_rent,
                security_deposit=customer.security_deposit,
                advance_payment=0,
            )
            if check_in_now and customer.check_in_date and customer.check_in_date <= timezone.localdate():
                check_in(self.actor, reservation)
        customer = self.get_queryset().get(pk=customer.pk)
        return Response(CustomerDetailSerializer(customer).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        self.require("customers.manage")
        if "branch" in serializer.validated_data and serializer.validated_data["branch"]:
            require_branch(self.actor, serializer.validated_data["branch"])
        if self.actor["role"] != "owner" and serializer.instance.branch_id != self.actor["branch_id"]:
            raise PermissionDenied("You can only work inside your assigned branch.")
        customer = serializer.save()
        store_identity_docs(customer, self.request.user)

    def perform_destroy(self, instance):
        if self.actor["role"] == "employee":
            raise PermissionDenied("Employees cannot delete customers.")
        if instance.reservations.filter(status__in=["pending", "confirmed", "checked_in"]).exists():
            raise ValidationError({"detail": "Check this customer out or cancel the reservation first."})
        instance.is_deleted = True
        instance.status = HostelCustomer.Status.INACTIVE
        instance.save(update_fields=["is_deleted", "status", "updated_at"])

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = CustomerWriteSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("bed_id", None)
        serializer.validated_data.pop("check_in_now", None)
        self.perform_update(serializer)
        instance = self.get_queryset().get(pk=instance.pk)
        return Response(CustomerDetailSerializer(instance).data)

    @action(detail=True, methods=["post"], url_path="change-room")
    def change_room_action(self, request, pk=None):
        customer = self.get_object()
        bed = HostelBed.objects.get(pk=request.data.get("bed"), business=request.user.business)
        end = request.data.get("expected_checkout")
        moved = change_room(self.actor, customer, bed, parse_date(end, "expected_checkout") if end else None)
        return Response(ReservationSerializer(moved).data)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out_action(self, request, pk=None):
        customer = self.get_object()
        reservation = customer.reservations.filter(status=HostelReservation.Status.CHECKED_IN).first()
        if reservation is None:
            raise ValidationError({"detail": "This customer is not checked in."})
        reservation = check_out(self.actor, reservation, request.data.get("notes") or "")
        return Response(ReservationSerializer(reservation).data)


class ReservationViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    queryset = HostelReservation.objects.all()
    search_fields = ("number", "customer__full_name", "customer__mobile", "room__number", "bed__code")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "branch", "room", "bed")
        res_status = self.request.query_params.get("status")
        if res_status:
            qs = qs.filter(status=res_status)
        customer = self.request.query_params.get("customer")
        if customer:
            qs = qs.filter(customer_id=customer)
        room = self.request.query_params.get("room")
        if room:
            qs = qs.filter(room_id=room)
        return qs

    def create(self, request, *args, **kwargs):
        customer = HostelCustomer.objects.get(pk=request.data.get("customer"), business=request.user.business, is_deleted=False)
        bed = HostelBed.objects.select_related("room", "branch").get(pk=request.data.get("bed"), business=request.user.business)
        reservation = create_reservation(
            self.actor,
            customer=customer,
            bed=bed,
            reservation_date=parse_date(request.data.get("reservation_date") or timezone.localdate().isoformat(), "reservation_date"),
            check_in_date=parse_date(request.data.get("check_in_date"), "check_in_date"),
            expected_checkout=parse_date(request.data.get("expected_checkout"), "expected_checkout"),
            monthly_rent=request.data.get("monthly_rent"),
            security_deposit=request.data.get("security_deposit"),
            advance_payment=request.data.get("advance_payment") or 0,
            instructions=request.data.get("instructions") or "",
            status=request.data.get("status") or HostelReservation.Status.CONFIRMED,
            documents=request.data.get("documents") or [],
        )
        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in_action(self, request, pk=None):
        reservation = check_in(self.actor, self.get_object(), request.data.get("notes") or "")
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out_action(self, request, pk=None):
        reservation = check_out(self.actor, self.get_object(), request.data.get("notes") or "")
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(ReservationSerializer(cancel_reservation(self.actor, self.get_object())).data)

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        reservation = extend_stay(self.actor, self.get_object(), parse_date(request.data.get("expected_checkout"), "expected_checkout"))
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self.require("reservations.manage")
        reservation = self.get_object()
        if reservation.status != HostelReservation.Status.PENDING:
            raise ValidationError({"detail": "Only a pending reservation can be confirmed."})
        reservation.status = HostelReservation.Status.CONFIRMED
        reservation.save(update_fields=["status", "updated_at"])
        return Response(ReservationSerializer(reservation).data)


class PaymentViewSet(HostelBase, viewsets.ModelViewSet):
    queryset = HostelPayment.objects.all()
    search_fields = ("receipt_no", "transaction_id", "customer__full_name", "customer__mobile", "customer__cnic")
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PaymentDetailSerializer
        return PaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "branch", "room", "bed", "received_by")
        if self.actor["role"] == "employee":
            qs = qs.filter(received_by=self.request.user)
        for field, column in (
            ("customer", "customer_id"),
            ("payment_type", "payment_type"),
            ("method", "method"),
            ("employee", "received_by__hostel_employee__id"),
        ):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{column: value})
        if self.request.query_params.get("date_from"):
            qs = qs.filter(payment_date__gte=self.request.query_params["date_from"])
        if self.request.query_params.get("date_to"):
            qs = qs.filter(payment_date__lte=self.request.query_params["date_to"])
        if self.request.query_params.get("room"):
            qs = qs.filter(room_id=self.request.query_params["room"])
        if self.request.query_params.get("voided") != "1":
            qs = qs.filter(is_void=False)
        return qs

    def create(self, request, *args, **kwargs):
        customer = HostelCustomer.objects.get(pk=request.data.get("customer"), business=request.user.business, is_deleted=False)
        reservation = None
        if request.data.get("reservation"):
            reservation = HostelReservation.objects.get(pk=request.data.get("reservation"), business=request.user.business)
        payment = record_payment(
            self.actor,
            customer=customer,
            amount=request.data.get("amount"),
            payment_type=request.data.get("payment_type") or HostelPayment.Type.RENT,
            method=request.data.get("method") or HostelPayment.Method.CASH,
            payment_date=parse_date(request.data.get("payment_date") or timezone.localdate().isoformat(), "payment_date"),
            year=request.data.get("period_year"),
            month=request.data.get("period_month"),
            transaction_id=request.data.get("transaction_id") or "",
            notes=request.data.get("notes") or "",
            receipt_image=request.data.get("receipt_image") or "",
            screenshot=request.data.get("screenshot") or "",
            reservation=reservation,
        )
        return Response(PaymentDetailSerializer(payment).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        void_payment(self.actor, instance)


class MonthlyViewSet(HostelBase, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = MonthlySerializer
    queryset = HostelMonthlyRent.objects.all()
    search_fields = ("customer__full_name", "customer__mobile", "invoice_number")

    def get_queryset(self):
        refresh_overdue()
        qs = super().get_queryset().select_related("customer", "customer__room", "customer__bed", "branch")
        bill_status = self.request.query_params.get("status")
        customer = self.request.query_params.get("customer")
        year = self.request.query_params.get("year")
        month = self.request.query_params.get("month")
        if bill_status:
            qs = qs.filter(status=bill_status)
        if customer:
            qs = qs.filter(customer_id=customer)
        if year:
            qs = qs.filter(year=year)
        if month:
            qs = qs.filter(month=month)
        return qs

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        bill = adjust_bill(
            self.actor,
            self.get_object(),
            late_fee=request.data.get("late_fee"),
            discount=request.data.get("discount"),
            extra=request.data.get("extra_charges"),
        )
        return Response(MonthlySerializer(bill).data)


class ExpenseViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    queryset = HostelExpense.objects.all()
    search_fields = ("title", "category")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "recorded_by")
        if self.actor["role"] == "employee":
            qs = qs.filter(recorded_by=self.request.user)
        approval = self.request.query_params.get("approval")
        if approval:
            qs = qs.filter(approval=approval)
        return qs

    def perform_create(self, serializer):
        self.require("expenses.submit")
        branch = require_branch(self.actor, serializer.validated_data["branch"])
        serializer.save(business=self.request.user.business, branch=branch, recorded_by=self.request.user, approval=HostelExpense.Approval.PENDING)
        from apps.hostel.services import audit, notify
        expense = serializer.instance
        audit(self.request.user.business, self.request.user, "expense.submitted", f"{expense.title} · Rs {expense.amount}", branch, "expense", expense.pk)
        notify(self.request.user.business, "expense", "Expense submitted", expense.title, "/hostel/expenses", branch)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self.require("expenses.approve")
        expense = self.get_object()
        decision = request.data.get("approval")
        if decision not in (HostelExpense.Approval.APPROVED, HostelExpense.Approval.REJECTED):
            raise ValidationError({"approval": "Choose approved or rejected."})
        expense.approval = decision
        expense.approved_by = request.user
        expense.save(update_fields=["approval", "approved_by", "updated_at"])
        return Response(ExpenseSerializer(expense).data)


class MaintenanceViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = MaintenanceSerializer
    queryset = HostelMaintenance.objects.all()
    search_fields = ("title", "assigned_worker")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "room", "reported_by")
        job_status = self.request.query_params.get("status")
        if job_status:
            qs = qs.filter(status=job_status)
        return qs

    def perform_create(self, serializer):
        self.require("maintenance.submit")
        branch = require_branch(self.actor, serializer.validated_data["branch"])
        images = clean_images(serializer.validated_data.get("images"))
        serializer.save(business=self.request.user.business, branch=branch, reported_by=self.request.user, images=images, status=HostelMaintenance.Status.PENDING)
        job = serializer.instance
        from apps.hostel.services import audit, notify
        audit(self.request.user.business, self.request.user, "maintenance.reported", job.title, branch, "maintenance", job.pk)
        notify(self.request.user.business, "maintenance", "Maintenance request", job.title, "/hostel/expenses", branch)

    def perform_update(self, serializer):
        if self.actor["role"] == "employee":
            raise PermissionDenied("Ask a manager to update this maintenance request.")
        self.require("maintenance.manage")
        if "images" in serializer.validated_data:
            serializer.validated_data["images"] = clean_images(serializer.validated_data.get("images"))
        serializer.save()


class EmployeeViewSet(HostelBase, viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    queryset = HostelEmployee.objects.all()
    pagination_class = None
    search_fields = ("full_name", "email", "phone", "employee_code", "designation")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "user").prefetch_related("permissions")
        if self.actor["role"] == "employee":
            qs = qs.filter(user=self.request.user)
        month = timezone.localdate().replace(day=1)
        return qs.annotate(
            collected_amount=Sum(
                "user__hostel_payments_received__amount",
                filter=Q(user__hostel_payments_received__is_void=False, user__hostel_payments_received__payment_date__gte=month),
            ),
            collected_count=Count(
                "user__hostel_payments_received",
                filter=Q(user__hostel_payments_received__is_void=False, user__hostel_payments_received__payment_date__gte=month),
            ),
        )

    def create(self, request, *args, **kwargs):
        if self.actor["role"] != "owner":
            branch = HostelBranch.objects.get(pk=self.actor["branch_id"], business=request.user.business, is_deleted=False)
        elif not request.data.get("branch"):
            raise ValidationError({"branch": "Choose a branch."})
        else:
            branch = HostelBranch.objects.get(pk=request.data.get("branch"), business=request.user.business, is_deleted=False)
        payload = {
            "branch": branch,
            "full_name": request.data.get("full_name") or "",
            "email": request.data.get("email") or "",
            "phone": request.data.get("phone") or "",
            "photo": request.data.get("photo") or "",
            "designation": request.data.get("designation") or "",
            "salary": request.data.get("salary") or 0,
            "joining_date": parse_date(request.data.get("joining_date"), "joining_date") if request.data.get("joining_date") else None,
            "role": request.data.get("role") or HostelEmployee.Role.EMPLOYEE,
            "password": request.data.get("password") or "",
            "can_manage_staff": bool(request.data.get("can_manage_staff")),
            "can_approve_expenses": bool(request.data.get("can_approve_expenses")),
            "can_view_reports": bool(request.data.get("can_view_reports")),
        }
        if not payload["full_name"]:
            raise ValidationError({"full_name": "Enter the employee name."})
        employee, token = create_employee(self.actor, payload)
        data = EmployeeSerializer(self.get_queryset().get(pk=employee.pk)).data
        if token:
            data["invite_path"] = f"/hostel/invite?token={token}"
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if self.actor["role"] != "owner":
            raise PermissionDenied("Only the owner can change staff access.")
        employee = serializer.save()
        if employee.role != HostelEmployee.Role.MANAGER:
            employee.can_manage_staff = False
            employee.can_approve_expenses = False
            employee.save(update_fields=["can_manage_staff", "can_approve_expenses", "updated_at"])
        assign_permissions(employee)

    def perform_destroy(self, instance):
        self.require("staff.manage")
        if self.actor["employee"] and instance.pk == self.actor["employee"].pk:
            raise ValidationError({"detail": "You cannot remove your own account."})
        if self.actor["role"] != "owner" and instance.role == HostelEmployee.Role.MANAGER:
            raise PermissionDenied("Only the owner can remove a manager.")
        instance.is_deleted = True
        instance.status = HostelEmployee.Status.INACTIVE
        instance.save(update_fields=["is_deleted", "status", "updated_at"])
        if instance.user_id:
            instance.user.is_active = False
            instance.user.save(update_fields=["is_active"])

    @action(detail=False, methods=["get"])
    def collections(self, request):
        if self.actor["role"] == "employee":
            qs = self.get_queryset().filter(user=request.user)
        else:
            self.require("reports.branch" if self.actor["role"] != "owner" else "reports.owner")
            qs = self.get_queryset()
        return Response(EmployeeSerializer(qs, many=True).data)


class DocumentViewSet(HostelBase, viewsets.ModelViewSet):
    queryset = HostelDocument.objects.all()
    search_fields = ("title", "file_name", "customer__full_name")
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("retrieve", "create"):
            return DocumentDetailSerializer
        return DocumentSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "branch")
        customer = self.request.query_params.get("customer")
        kind = self.request.query_params.get("kind")
        if customer:
            qs = qs.filter(customer_id=customer)
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer):
        self.require("documents.manage")
        customer = serializer.validated_data.get("customer")
        branch = serializer.validated_data.get("branch") or (customer.branch if customer else None)
        if branch:
            require_branch(self.actor, branch)
        if customer and self.actor["role"] != "owner" and customer.branch_id != self.actor["branch_id"]:
            raise PermissionDenied("You can only work inside your assigned branch.")
        file_data = serializer.validated_data.get("file_data")
        if not file_data:
            raise ValidationError({"file_data": "Choose a file."})
        serializer.save(business=self.request.user.business, branch=branch, uploaded_by=self.request.user)

    def perform_destroy(self, instance):
        if self.actor["role"] == "employee":
            raise PermissionDenied("Employees cannot delete documents.")
        self.require("documents.manage")
        instance.delete()


class NotificationViewSet(HostelBase, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    queryset = HostelNotification.objects.all()

    def get_queryset(self):
        qs = HostelNotification.objects.filter(business=self.request.user.business)
        if self.actor["role"] == "owner":
            qs = qs.filter(audience=HostelNotification.Audience.OWNER)
        else:
            qs = qs.filter(audience=HostelNotification.Audience.BRANCH, branch_id=self.actor["branch_id"])
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        note = self.get_queryset().get(pk=pk)
        note.is_read = True
        note.save(update_fields=["is_read", "updated_at"])
        return Response(NotificationSerializer(note).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"ok": True})


class AuditViewSet(HostelBase, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditSerializer
    queryset = HostelAuditLog.objects.all()
    search_fields = ("summary", "action", "actor__first_name", "actor__email")

    def get_queryset(self):
        qs = super().get_queryset().select_related("actor", "branch")
        if self.actor["role"] == "employee":
            qs = qs.filter(actor=self.request.user)
        action_name = self.request.query_params.get("action")
        if action_name:
            qs = qs.filter(action=action_name)
        employee = self.request.query_params.get("employee")
        if employee and self.actor["role"] != "employee":
            staff = HostelEmployee.objects.filter(pk=employee, business=self.request.user.business).first()
            if staff and staff.user_id:
                qs = qs.filter(actor_id=staff.user_id)
        return qs


class HostelMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        actor = actor_context(request.user)
        sheet = settings_for(actor["business"])
        employee = actor["employee"]
        return Response({
            "role": actor["role"],
            "branch_id": str(actor["branch_id"]) if actor["branch_id"] else None,
            "branch_name": employee.branch.name if employee else "",
            "employee_id": str(employee.id) if employee else None,
            "full_name": request.user.full_name,
            "permissions": sorted(permission_codes(actor)),
            "hostel_name": sheet.display_name or actor["business"].name,
            "logo": sheet.logo,
        })


class HostelDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        actor = actor_context(request.user)
        refresh_overdue()
        return Response(dashboard(actor, request.query_params))


class HostelSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(search_hostel(actor_context(request.user), request.query_params.get("q")))


class HostelReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        kind = request.query_params.get("type") or "occupancy"
        return Response(build_report(actor_context(request.user), kind, request.query_params))


class HostelSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        actor = actor_context(request.user)
        return Response(SettingsSerializer(settings_for(actor["business"])).data)

    def put(self, request):
        actor = actor_context(request.user)
        ensure_perm(actor, "settings.manage")
        sheet = settings_for(actor["business"])
        serializer = SettingsSerializer(sheet, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class BillingGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        actor = actor_context(request.user)
        today = timezone.localdate()
        year = int(request.data.get("year") or today.year)
        month = int(request.data.get("month") or today.month)
        created = generate_months(actor, year, month, request.data.get("branch"))
        return Response({"created": created, "year": year, "month": month})


class BillingLateFeeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        actor = actor_context(request.user)
        count = apply_late_fees(actor, request.data.get("branch"))
        return Response({"updated": count})


class InviteAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        accept_invite(request.data.get("token") or "", request.data.get("password") or "")
        return Response({"detail": "Password saved. You can sign in now."})
