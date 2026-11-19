from rest_framework import serializers

from apps.hostel.models import (
    HostelAuditLog,
    HostelBed,
    HostelBranch,
    HostelCheckIn,
    HostelCheckOut,
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
    HostelSettings,
)
from apps.hostel.services import clean_upload, finance_dict, money


class BranchSerializer(serializers.ModelSerializer):
    total_rooms = serializers.IntegerField(read_only=True)
    total_seats = serializers.IntegerField(read_only=True)
    available_seats = serializers.IntegerField(read_only=True)
    occupied_seats = serializers.IntegerField(read_only=True)
    reserved_seats = serializers.IntegerField(read_only=True)
    image = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = HostelBranch
        fields = (
            "id", "name", "code", "address", "city", "phone", "email", "manager_name",
            "floors", "monthly_rent", "security_deposit", "opening_date", "status", "image",
            "total_rooms", "total_seats", "available_seats", "occupied_seats", "reserved_seats",
            "created_at",
        )

    def validate_image(self, value):
        return clean_upload(value, label="image")

    def validate_code(self, value):
        return value.strip().upper()


class BedSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True)
    floor = serializers.IntegerField(source="room.floor", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    occupant = serializers.SerializerMethodField()
    monthly_rent = serializers.DecimalField(source="room.monthly_rent", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = HostelBed
        fields = ("id", "code", "status", "room", "room_number", "floor", "branch", "branch_name", "occupant", "monthly_rent")

    def get_occupant(self, obj):
        stay = obj.reservations.filter(status="checked_in").select_related("customer").first()
        if stay is None:
            stay = obj.reservations.filter(status__in=["confirmed", "pending"]).select_related("customer").first()
        if stay is None:
            return None
        return {"id": str(stay.customer_id), "name": stay.customer.full_name, "reservation": str(stay.id)}


class RoomSerializer(serializers.ModelSerializer):
    beds = BedSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    occupied_beds = serializers.SerializerMethodField()
    available_beds = serializers.SerializerMethodField()
    image = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = HostelRoom
        fields = (
            "id", "branch", "branch_name", "number", "floor", "room_type", "capacity",
            "monthly_rent", "security_deposit", "attached_bathroom", "ac", "wifi",
            "facilities", "image", "status", "beds", "occupied_beds", "available_beds",
        )

    def validate_image(self, value):
        return clean_upload(value, label="image")

    def get_occupied_beds(self, obj):
        return sum(1 for bed in obj.beds.all() if bed.status == "occupied")

    def get_available_beds(self, obj):
        return sum(1 for bed in obj.beds.all() if bed.status == "available")


class RoomWriteSerializer(RoomSerializer):
    class Meta(RoomSerializer.Meta):
        extra_kwargs = {"capacity": {"required": False}}


class CustomerListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    seat = serializers.CharField(source="bed.code", read_only=True)
    floor = serializers.IntegerField(source="room.floor", read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = HostelCustomer
        fields = (
            "id", "full_name", "father_name", "mobile", "whatsapp", "email", "gender",
            "cnic", "branch", "branch_name", "room", "room_number", "floor", "bed", "seat",
            "admission_date", "check_in_date", "expected_checkout", "checkout_date",
            "monthly_rent", "security_deposit", "registration_fee", "status", "balance",
        )

    def get_balance(self, obj):
        return finance_dict(obj)["remaining"]


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = HostelDocument
        fields = ("id", "title", "kind", "file_name", "customer", "branch", "created_at")


class DocumentDetailSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ("file_data",)

    def validate_file_data(self, value):
        return clean_upload(value, allow_pdf=True, label="file_data")


class ReservationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="customer.mobile", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    floor = serializers.IntegerField(source="room.floor", read_only=True)
    seat = serializers.CharField(source="bed.code", read_only=True)

    class Meta:
        model = HostelReservation
        fields = (
            "id", "number", "branch", "branch_name", "room", "room_number", "floor", "bed", "seat",
            "customer", "customer_name", "customer_phone", "reservation_date", "check_in_date",
            "expected_checkout", "monthly_rent", "security_deposit", "advance_payment",
            "advance_posted", "instructions", "status", "created_at",
        )


class StayEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    at = serializers.DateTimeField()
    notes = serializers.CharField()
    room = serializers.CharField()
    seat = serializers.CharField()
    by = serializers.CharField()


class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    seat = serializers.CharField(source="bed.code", read_only=True)
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = HostelPayment
        fields = (
            "id", "receipt_no", "customer", "customer_name", "branch", "branch_name", "room",
            "room_number", "bed", "seat", "reservation", "payment_type", "amount", "payment_date",
            "period_year", "period_month", "method", "transaction_id", "notes", "received_by",
            "received_by_name", "is_void", "created_at",
        )

    def get_received_by_name(self, obj):
        return obj.received_by.full_name if obj.received_by_id else ""


class PaymentDetailSerializer(PaymentSerializer):
    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + ("receipt_image", "screenshot")


class MonthlySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    room_number = serializers.CharField(source="customer.room.number", read_only=True)
    seat = serializers.CharField(source="customer.bed.code", read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = HostelMonthlyRent
        fields = (
            "id", "customer", "customer_name", "branch", "branch_name", "room_number", "seat",
            "year", "month", "rent_amount", "late_fee", "discount", "extra_charges",
            "amount_due", "amount_paid", "balance", "due_date", "status", "invoice_number",
        )

    def get_balance(self, obj):
        return str(max(money(0), obj.amount_due - obj.amount_paid))


class ExpenseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    receipt_image = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = HostelExpense
        fields = (
            "id", "branch", "branch_name", "title", "category", "amount", "expense_date",
            "description", "method", "receipt_image", "approval", "recorded_by", "recorded_by_name",
            "created_at",
        )
        read_only_fields = ("approval", "recorded_by")

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by_id else ""

    def validate_receipt_image(self, value):
        return clean_upload(value, allow_pdf=True, label="receipt_image")


class MaintenanceSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    reported_by_name = serializers.SerializerMethodField()

    class Meta:
        model = HostelMaintenance
        fields = (
            "id", "branch", "branch_name", "room", "room_number", "title", "description", "images",
            "reported_by", "reported_by_name", "assigned_worker", "priority", "estimated_cost",
            "actual_cost", "status", "completion_date", "created_at",
        )
        read_only_fields = ("reported_by",)

    def get_reported_by_name(self, obj):
        return obj.reported_by.full_name if obj.reported_by_id else ""


class EmployeeSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    permissions = serializers.SerializerMethodField()
    collected = serializers.SerializerMethodField()
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = HostelEmployee
        fields = (
            "id", "employee_code", "full_name", "email", "phone", "photo", "branch", "branch_name",
            "designation", "salary", "joining_date", "role", "status", "can_manage_staff",
            "can_approve_expenses", "can_view_reports", "permissions", "collected", "transactions",
        )
        read_only_fields = ("employee_code", "status")

    def get_permissions(self, obj):
        return list(obj.permissions.values_list("codename", flat=True))

    def get_collected(self, obj):
        return str(getattr(obj, "collected_amount", None) or 0)

    def get_transactions(self, obj):
        return int(getattr(obj, "collected_count", None) or 0)

    def validate_photo(self, value):
        return clean_upload(value, label="photo")


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HostelNotification
        fields = ("id", "kind", "title", "body", "href", "is_read", "branch", "created_at")


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = HostelAuditLog
        fields = ("id", "action", "summary", "entity", "entity_id", "actor_name", "branch_name", "created_at")

    def get_actor_name(self, obj):
        return obj.actor.full_name if obj.actor_id else ""


class SettingsSerializer(serializers.ModelSerializer):
    logo = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = HostelSettings
        fields = ("display_name", "tagline", "logo", "due_day", "late_fee", "receipt_prefix")

    def validate_logo(self, value):
        return clean_upload(value, label="logo")

    def validate_due_day(self, value):
        if value < 1 or value > 28:
            raise serializers.ValidationError("Use a due day from 1 to 28.")
        return value


class CustomerDetailSerializer(CustomerListSerializer):
    photo = serializers.CharField(required=False, allow_blank=True)
    cnic_front = serializers.CharField(required=False, allow_blank=True)
    cnic_back = serializers.CharField(required=False, allow_blank=True)
    finance = serializers.SerializerMethodField()
    reservations = ReservationSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    months = MonthlySerializer(source="monthly_rents", many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    checkins = serializers.SerializerMethodField()
    checkouts = serializers.SerializerMethodField()

    class Meta(CustomerListSerializer.Meta):
        fields = CustomerListSerializer.Meta.fields + (
            "date_of_birth", "permanent_address", "current_address", "emergency_contact",
            "guardian_name", "guardian_contact", "photo", "cnic_front", "cnic_back", "notes",
            "credit", "finance", "reservations", "payments", "months", "documents", "checkins", "checkouts",
        )

    def validate_photo(self, value):
        return clean_upload(value, label="photo")

    def validate_cnic_front(self, value):
        return clean_upload(value, label="cnic_front")

    def validate_cnic_back(self, value):
        return clean_upload(value, label="cnic_back")

    def get_finance(self, obj):
        return finance_dict(obj)

    def get_checkins(self, obj):
        return [
            {"id": str(row.id), "at": row.checked_in_at, "notes": row.notes, "seat": row.bed.code, "room": row.bed.room.number, "by": row.performed_by.full_name if row.performed_by_id else ""}
            for row in obj.checkins.select_related("bed__room", "performed_by")
        ]

    def get_checkouts(self, obj):
        return [
            {"id": str(row.id), "at": row.checked_out_at, "notes": row.notes, "seat": row.bed.code, "room": row.bed.room.number, "by": row.performed_by.full_name if row.performed_by_id else ""}
            for row in obj.checkouts.select_related("bed__room", "performed_by")
        ]


class CustomerWriteSerializer(serializers.ModelSerializer):
    photo = serializers.CharField(required=False, allow_blank=True)
    cnic_front = serializers.CharField(required=False, allow_blank=True)
    cnic_back = serializers.CharField(required=False, allow_blank=True)
    bed_id = serializers.UUIDField(required=False, allow_null=True)
    check_in_now = serializers.BooleanField(required=False)

    class Meta:
        model = HostelCustomer
        fields = (
            "full_name", "father_name", "mobile", "whatsapp", "email", "gender", "date_of_birth",
            "permanent_address", "current_address", "emergency_contact", "guardian_name",
            "guardian_contact", "cnic", "photo", "cnic_front", "cnic_back", "branch",
            "admission_date", "check_in_date", "expected_checkout", "monthly_rent",
            "security_deposit", "registration_fee", "status", "notes", "bed_id", "check_in_now",
        )
        extra_kwargs = {"branch": {"required": False, "allow_null": True}}

    def validate_photo(self, value):
        return clean_upload(value, label="photo")

    def validate_cnic_front(self, value):
        return clean_upload(value, label="cnic_front")

    def validate_cnic_back(self, value):
        return clean_upload(value, label="cnic_back")
