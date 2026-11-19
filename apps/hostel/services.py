import calendar
import hashlib
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.hostel.access import actor_context, codes_for_employee, ensure_perm, has_perm
from apps.hostel.models import (
    HostelAuditLog,
    HostelBed,
    HostelBranch,
    HostelCheckIn,
    HostelCheckOut,
    HostelCustomer,
    HostelDocument,
    HostelEmployee,
    HostelEmployeePermission,
    HostelExpense,
    HostelInvoice,
    HostelMaintenance,
    HostelMonthlyRent,
    HostelNotification,
    HostelPayment,
    HostelReservation,
    HostelRoom,
    HostelSettings,
)

User = get_user_model()
ZERO = Decimal("0.00")
OPEN_BOOKINGS = [
    HostelReservation.Status.PENDING,
    HostelReservation.Status.CONFIRMED,
    HostelReservation.Status.CHECKED_IN,
]
CHARGE_TYPES = {
    HostelPayment.Type.ELECTRICITY,
    HostelPayment.Type.GAS,
    HostelPayment.Type.LAUNDRY,
    HostelPayment.Type.INTERNET,
    HostelPayment.Type.OTHER,
}
RENT_TYPES = {HostelPayment.Type.RENT, HostelPayment.Type.ADVANCE}
MAX_UPLOAD = 1_600_000
IMAGE_PREFIXES = ("data:image/jpeg", "data:image/jpg", "data:image/png", "data:image/webp")
PDF_PREFIXES = ("data:application/pdf",)


def money(value) -> Decimal:
    try:
        amount = Decimal(str(value if value not in (None, "") else "0"))
    except Exception as exc:
        raise ValidationError({"amount": "Enter a valid amount."}) from exc
    return amount.quantize(Decimal("0.01"))


def clean_upload(value, *, allow_pdf=False, label="file"):
    if not value:
        return ""
    text = str(value).strip()
    if len(text) > MAX_UPLOAD:
        raise ValidationError({label: "File is too large. Keep it under 1.2 MB."})
    allowed = IMAGE_PREFIXES + (PDF_PREFIXES if allow_pdf else ())
    if not text.startswith(allowed) or ";base64," not in text:
        kind = "JPG, PNG, WEBP, or PDF" if allow_pdf else "JPG, PNG, or WEBP"
        raise ValidationError({label: f"Upload a {kind} file."})
    return text


def clean_images(values):
    if not values:
        return []
    if not isinstance(values, list):
        raise ValidationError({"images": "Upload images as a list."})
    if len(values) > 4:
        raise ValidationError({"images": "Upload up to 4 images."})
    return [clean_upload(item, label="images") for item in values if item]


def settings_for(business):
    row, _created = HostelSettings.objects.get_or_create(business=business)
    return row


def locked_settings(business):
    row = settings_for(business)
    return HostelSettings.objects.select_for_update().get(pk=row.pk)


def take_number(business, kind):
    sheet = locked_settings(business)
    if kind == "receipt":
        number = sheet.next_receipt
        sheet.next_receipt = number + 1
        sheet.save(update_fields=["next_receipt", "updated_at"])
        return f"{sheet.receipt_prefix or 'HST'}-{number:06d}"
    if kind == "reservation":
        number = sheet.next_reservation
        sheet.next_reservation = number + 1
        sheet.save(update_fields=["next_reservation", "updated_at"])
        return f"RSV-{number:06d}"
    if kind == "employee":
        number = sheet.next_employee
        sheet.next_employee = number + 1
        sheet.save(update_fields=["next_employee", "updated_at"])
        return f"EMP-{number:04d}"
    number = sheet.next_invoice
    sheet.next_invoice = number + 1
    sheet.save(update_fields=["next_invoice", "updated_at"])
    return f"INV-{number:06d}"


def audit(business, actor, action, summary, branch=None, entity="", entity_id=""):
    HostelAuditLog.objects.create(
        business=business,
        branch=branch,
        actor=actor,
        action=action,
        summary=summary[:255],
        entity=entity,
        entity_id=str(entity_id or ""),
    )


def notify(business, kind, title, body="", href="", branch=None):
    HostelNotification.objects.create(
        business=business,
        branch=branch,
        audience=HostelNotification.Audience.OWNER,
        kind=kind,
        title=title[:160],
        body=body[:400],
        href=href,
    )
    if branch is not None:
        HostelNotification.objects.create(
            business=business,
            branch=branch,
            audience=HostelNotification.Audience.BRANCH,
            kind=kind,
            title=title[:160],
            body=body[:400],
            href=href,
        )


def require_branch(actor, branch):
    if branch is None or branch.business_id != actor["business"].id or branch.is_deleted:
        raise ValidationError({"branch": "Choose a branch in this hostel."})
    if actor["role"] != "owner" and branch.id != actor["branch_id"]:
        raise PermissionDenied("You can only work inside your assigned branch.")
    return branch


def same_customer(actor, customer):
    if customer.business_id != actor["business"].id or customer.is_deleted:
        raise PermissionDenied("Customer not found.")
    if actor["role"] != "owner" and customer.branch_id != actor["branch_id"]:
        raise PermissionDenied("You can only work inside your assigned branch.")


def month_end(year, month):
    return calendar.monthrange(year, month)[1]


def due_on(business, year, month):
    sheet = settings_for(business)
    day = min(max(int(sheet.due_day or 5), 1), month_end(year, month))
    return date(year, month, day)


def bill_status(bill, today=None):
    today = today or timezone.localdate()
    if bill.amount_due <= ZERO or bill.amount_paid >= bill.amount_due:
        return HostelMonthlyRent.Status.PAID
    if bill.due_date and bill.due_date < today:
        return HostelMonthlyRent.Status.OVERDUE
    if bill.amount_paid > ZERO:
        return HostelMonthlyRent.Status.PARTIAL
    return HostelMonthlyRent.Status.UNPAID


def recompute_bill(bill):
    gross = bill.rent_amount + bill.late_fee + bill.extra_charges - bill.discount
    bill.amount_due = max(ZERO, gross)
    if bill.amount_paid > bill.amount_due:
        extra = bill.amount_paid - bill.amount_due
        bill.amount_paid = bill.amount_due
        customer = HostelCustomer.objects.select_for_update().get(pk=bill.customer_id)
        customer.credit = customer.credit + extra
        customer.save(update_fields=["credit", "updated_at"])
    bill.status = bill_status(bill)
    return bill


def sync_bed(bed):
    bed.refresh_from_db()
    open_qs = bed.reservations.filter(status__in=OPEN_BOOKINGS)
    if bed.status in (HostelBed.Status.MAINTENANCE, HostelBed.Status.BLOCKED):
        if open_qs.filter(status=HostelReservation.Status.CHECKED_IN).exists():
            bed.status = HostelBed.Status.OCCUPIED
            bed.save(update_fields=["status", "updated_at"])
        return bed
    if open_qs.filter(status=HostelReservation.Status.CHECKED_IN).exists():
        status = HostelBed.Status.OCCUPIED
    elif open_qs.exists():
        status = HostelBed.Status.RESERVED
    else:
        status = HostelBed.Status.AVAILABLE
    if bed.status != status:
        bed.status = status
        bed.save(update_fields=["status", "updated_at"])
    return bed


def overlapping(bed, start, end, exclude=None):
    qs = HostelReservation.objects.select_for_update().filter(
        bed=bed,
        status__in=OPEN_BOOKINGS,
        check_in_date__lt=end,
        expected_checkout__gt=start,
    )
    if exclude:
        qs = qs.exclude(pk=exclude)
    return qs


def assert_bed_free(bed, start, end, exclude=None):
    if start >= end:
        raise ValidationError({"expected_checkout": "Checkout must be after check-in."})
    if bed.status in (HostelBed.Status.MAINTENANCE, HostelBed.Status.BLOCKED):
        raise ValidationError({"bed": "This seat is not available."})
    if bed.room.status != HostelRoom.Status.ACTIVE or bed.room.is_deleted:
        raise ValidationError({"room": "This room is not open for booking."})
    if bed.branch.status != HostelBranch.Status.ACTIVE:
        raise ValidationError({"branch": "This branch is inactive."})
    if overlapping(bed, start, end, exclude).exists():
        raise ValidationError({"bed": "This seat is already booked for those dates."})


def capacity_for(room_type, capacity):
    fixed = {
        HostelRoom.RoomType.SINGLE: 1,
        HostelRoom.RoomType.DOUBLE: 2,
        HostelRoom.RoomType.TRIPLE: 3,
        HostelRoom.RoomType.FOUR: 4,
        HostelRoom.RoomType.SIX: 6,
    }
    if room_type in fixed:
        return fixed[room_type]
    count = int(capacity or 0)
    if count < 1 or count > 30:
        raise ValidationError({"capacity": "Custom rooms need 1 to 30 seats."})
    return count


def sync_room_beds(room):
    wanted = capacity_for(room.room_type, room.capacity)
    room.capacity = wanted
    beds = list(room.beds.order_by("code"))
    if wanted > len(beds):
        for index in range(len(beds) + 1, wanted + 1):
            HostelBed.objects.create(
                business=room.business,
                branch=room.branch,
                room=room,
                code=str(index),
                status=HostelBed.Status.MAINTENANCE if room.status == HostelRoom.Status.MAINTENANCE else HostelBed.Status.AVAILABLE,
            )
    elif wanted < len(beds):
        extra = beds[wanted:]
        busy = [bed for bed in extra if bed.reservations.filter(status__in=OPEN_BOOKINGS).exists() or bed.status == HostelBed.Status.OCCUPIED]
        if busy:
            raise ValidationError({"capacity": "Remove guests from the extra seats before lowering capacity."})
        HostelBed.objects.filter(pk__in=[bed.pk for bed in extra]).delete()
    room.save(update_fields=["capacity", "updated_at"])


def apply_credit(customer, bill):
    gap = bill.amount_due - bill.amount_paid
    if gap <= ZERO or customer.credit <= ZERO:
        return
    take = min(gap, customer.credit)
    bill.amount_paid += take
    customer.credit -= take
    customer.save(update_fields=["credit", "updated_at"])


def ensure_month(customer, year, month, reservation=None):
    year = int(year)
    month = int(month)
    if month < 1 or month > 12:
        raise ValidationError({"month": "Choose a valid month."})
    bill = HostelMonthlyRent.objects.select_for_update().filter(customer=customer, year=year, month=month).first()
    if bill:
        bill.status = bill_status(bill)
        bill.save(update_fields=["status", "updated_at"])
        return bill
    customer = HostelCustomer.objects.select_for_update().get(pk=customer.pk)
    bill = HostelMonthlyRent(
        business=customer.business,
        branch=customer.branch,
        customer=customer,
        reservation=reservation,
        year=year,
        month=month,
        rent_amount=customer.monthly_rent or ZERO,
        due_date=due_on(customer.business, year, month),
    )
    bill.amount_due = bill.rent_amount
    bill.status = bill_status(bill)
    apply_credit(customer, bill)
    bill.status = bill_status(bill)
    bill.invoice_number = take_number(customer.business, "invoice")
    bill.save()
    HostelInvoice.objects.create(
        business=customer.business,
        customer=customer,
        monthly_rent=bill,
        number=bill.invoice_number,
        total=bill.amount_due,
    )
    return bill


def apply_to_bills(customer, amount, preferred=None):
    left = money(amount)
    applications = []
    bills = list(
        HostelMonthlyRent.objects.select_for_update().filter(customer=customer).order_by("year", "month")
    )
    if preferred is not None:
        bills.sort(key=lambda row: (row.pk != preferred.pk, row.year, row.month))
    for bill in bills:
        gap = bill.amount_due - bill.amount_paid
        if gap <= ZERO or left <= ZERO:
            continue
        take = min(gap, left)
        bill.amount_paid += take
        bill.status = bill_status(bill)
        bill.save(update_fields=["amount_paid", "status", "updated_at"])
        applications.append({"bill": str(bill.pk), "amount": str(take)})
        left -= take
    credit_added = left if left > ZERO else ZERO
    if credit_added > ZERO:
        customer.credit += credit_added
        customer.save(update_fields=["credit", "updated_at"])
    return applications, credit_added


def generate_months(actor, year, month, branch_id=None):
    ensure_perm(actor, "payments.collect")
    qs = HostelCustomer.objects.filter(
        business=actor["business"],
        is_deleted=False,
        status=HostelCustomer.Status.ACTIVE,
    )
    if actor["role"] != "owner":
        qs = qs.filter(branch_id=actor["branch_id"])
    elif branch_id:
        qs = qs.filter(branch_id=branch_id)
    created = 0
    with transaction.atomic():
        for customer in qs.select_for_update():
            before = HostelMonthlyRent.objects.filter(customer=customer, year=year, month=month).exists()
            ensure_month(customer, year, month)
            if not before:
                created += 1
    return created


def adjust_bill(actor, bill, late_fee=None, discount=None, extra=None):
    if actor["role"] == "employee":
        raise PermissionDenied("Only a manager or owner can change a bill.")
    ensure_perm(actor, "payments.collect")
    same_customer(actor, bill.customer)
    with transaction.atomic():
        bill = HostelMonthlyRent.objects.select_for_update().get(pk=bill.pk)
        if late_fee is not None:
            bill.late_fee = money(late_fee)
        if discount is not None:
            bill.discount = money(discount)
        if extra is not None:
            bill.extra_charges = money(extra)
        if bill.discount > bill.rent_amount + bill.late_fee + bill.extra_charges:
            raise ValidationError({"discount": "Discount cannot be more than the bill."})
        recompute_bill(bill)
        bill.save()
        if hasattr(bill, "invoice"):
            bill.invoice.total = bill.amount_due
            bill.invoice.save(update_fields=["total", "updated_at"])
    return bill


def apply_late_fees(actor, branch_id=None):
    if actor["role"] == "employee":
        raise PermissionDenied("Only a manager or owner can add late fees.")
    fee = settings_for(actor["business"]).late_fee
    if fee <= ZERO:
        raise ValidationError({"late_fee": "Set a late fee in hostel settings first."})
    today = timezone.localdate()
    qs = HostelMonthlyRent.objects.filter(
        business=actor["business"],
        due_date__lt=today,
        late_fee=ZERO,
    ).exclude(status=HostelMonthlyRent.Status.PAID)
    if actor["role"] != "owner":
        qs = qs.filter(branch_id=actor["branch_id"])
    elif branch_id:
        qs = qs.filter(branch_id=branch_id)
    count = 0
    with transaction.atomic():
        for bill in qs.select_for_update():
            if bill.amount_paid >= bill.amount_due:
                continue
            bill.late_fee = fee
            recompute_bill(bill)
            bill.save()
            count += 1
    return count


@transaction.atomic
def record_payment(actor, *, customer, amount, payment_type, method, payment_date, year=None, month=None,
                   transaction_id="", notes="", receipt_image="", screenshot="", reservation=None):
    ensure_perm(actor, "payments.collect")
    same_customer(actor, customer)
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({"amount": "Enter an amount greater than zero."})
    receipt_image = clean_upload(receipt_image, allow_pdf=True, label="receipt_image")
    screenshot = clean_upload(screenshot, label="screenshot")
    customer = HostelCustomer.objects.select_for_update().get(pk=customer.pk)
    year = int(year or payment_date.year)
    month = int(month or payment_date.month)
    applications = []
    credit_amount = ZERO
    bill = None
    if payment_type in RENT_TYPES:
        bill = ensure_month(customer, year, month, reservation)
        applications, credit_amount = apply_to_bills(customer, amount, preferred=bill)
    elif payment_type in CHARGE_TYPES:
        bill = ensure_month(customer, year, month, reservation)
        bill.extra_charges += amount
        recompute_bill(bill)
        bill.amount_paid += amount
        if bill.amount_paid > bill.amount_due:
            spill = bill.amount_paid - bill.amount_due
            bill.amount_paid = bill.amount_due
            customer.credit += spill
            customer.save(update_fields=["credit", "updated_at"])
            credit_amount = spill
        bill.status = bill_status(bill)
        bill.save()
        applications = [{"bill": str(bill.pk), "amount": str(amount - credit_amount), "extra": str(amount)}]
    payment = HostelPayment.objects.create(
        business=actor["business"],
        branch=customer.branch,
        customer=customer,
        reservation=reservation,
        room=customer.room,
        bed=customer.bed,
        monthly_rent=bill,
        receipt_no=take_number(actor["business"], "receipt"),
        payment_type=payment_type,
        amount=amount,
        payment_date=payment_date,
        period_year=year,
        period_month=month,
        method=method or HostelPayment.Method.CASH,
        transaction_id=transaction_id or "",
        notes=notes or "",
        receipt_image=receipt_image,
        screenshot=screenshot,
        applications=applications,
        credit_amount=credit_amount,
        received_by=actor["user"],
    )
    if screenshot or receipt_image:
        HostelDocument.objects.create(
            business=actor["business"],
            branch=customer.branch,
            customer=customer,
            title=f"Receipt {payment.receipt_no}",
            kind=HostelDocument.Kind.PAYMENT,
            file_name=payment.receipt_no,
            file_data=screenshot or receipt_image,
            uploaded_by=actor["user"],
        )
    audit(actor["business"], actor["user"], "payment.received", f"{payment.receipt_no} · Rs {amount} · {customer.full_name}", customer.branch, "payment", payment.pk)
    notify(actor["business"], "payment", "Payment received", f"{customer.full_name} paid Rs {amount}.", f"/hostel/payments/history", customer.branch)
    return payment


def peel_credit(customer, left):
    bills = HostelMonthlyRent.objects.select_for_update().filter(customer=customer).order_by("-year", "-month")
    for bill in bills:
        if left <= ZERO:
            break
        take = min(bill.amount_paid, left)
        if take <= ZERO:
            continue
        bill.amount_paid -= take
        bill.status = bill_status(bill)
        bill.save(update_fields=["amount_paid", "status", "updated_at"])
        left -= take
    return left


@transaction.atomic
def void_payment(actor, payment):
    ensure_perm(actor, "payments.void")
    if payment.is_void:
        raise ValidationError({"detail": "This payment is already void."})
    same_customer(actor, payment.customer)
    customer = HostelCustomer.objects.select_for_update().get(pk=payment.customer_id)
    credit_left = payment.credit_amount
    if customer.credit >= credit_left:
        customer.credit -= credit_left
        credit_left = ZERO
    else:
        credit_left -= customer.credit
        customer.credit = ZERO
    customer.save(update_fields=["credit", "updated_at"])
    for row in payment.applications or []:
        bill = HostelMonthlyRent.objects.select_for_update().filter(pk=row.get("bill"), customer=customer).first()
        if bill is None:
            continue
        take = money(row.get("amount") or 0)
        bill.amount_paid = max(ZERO, bill.amount_paid - take)
        extra = money(row.get("extra") or 0)
        if extra > ZERO:
            bill.extra_charges = max(ZERO, bill.extra_charges - extra)
        recompute_bill(bill)
        bill.save()
    if credit_left > ZERO:
        peel_credit(customer, credit_left)
    payment.is_void = True
    payment.voided_at = timezone.now()
    payment.voided_by = actor["user"]
    payment.save(update_fields=["is_void", "voided_at", "voided_by", "updated_at"])
    audit(actor["business"], actor["user"], "payment.voided", f"Voided {payment.receipt_no}", payment.branch, "payment", payment.pk)
    return payment


def store_identity_docs(customer, user):
    pairs = [
        (customer.photo, HostelDocument.Kind.PHOTO, "Profile photo"),
        (customer.cnic_front, HostelDocument.Kind.CNIC_FRONT, "CNIC front"),
        (customer.cnic_back, HostelDocument.Kind.CNIC_BACK, "CNIC back"),
    ]
    for data, kind, title in pairs:
        if not data:
            continue
        HostelDocument.objects.filter(customer=customer, kind=kind).delete()
        HostelDocument.objects.create(
            business=customer.business,
            branch=customer.branch,
            customer=customer,
            title=title,
            kind=kind,
            file_name=title,
            file_data=data,
            uploaded_by=user,
        )


@transaction.atomic
def create_reservation(actor, *, customer, bed, reservation_date, check_in_date, expected_checkout,
                       monthly_rent, security_deposit, advance_payment, instructions="", status=None, documents=None):
    ensure_perm(actor, "reservations.manage")
    same_customer(actor, customer)
    bed = HostelBed.objects.select_for_update().select_related("room", "branch").get(pk=bed.pk)
    require_branch(actor, bed.branch)
    if customer.branch_id and customer.branch_id != bed.branch_id and actor["role"] != "owner":
        raise ValidationError({"customer": "This customer belongs to another branch."})
    assert_bed_free(bed, check_in_date, expected_checkout)
    status = status or HostelReservation.Status.CONFIRMED
    if status not in (HostelReservation.Status.PENDING, HostelReservation.Status.CONFIRMED):
        status = HostelReservation.Status.CONFIRMED
    reservation = HostelReservation.objects.create(
        business=actor["business"],
        branch=bed.branch,
        room=bed.room,
        bed=bed,
        customer=customer,
        number=take_number(actor["business"], "reservation"),
        reservation_date=reservation_date or timezone.localdate(),
        check_in_date=check_in_date,
        expected_checkout=expected_checkout,
        monthly_rent=money(monthly_rent if monthly_rent is not None else bed.room.monthly_rent),
        security_deposit=money(security_deposit if security_deposit is not None else bed.room.security_deposit),
        advance_payment=money(advance_payment or 0),
        instructions=instructions or "",
        status=status,
        created_by=actor["user"],
    )
    if customer.branch_id is None:
        customer.branch = bed.branch
    if customer.bed_id is None:
        customer.status = HostelCustomer.Status.RESERVED
    if not customer.monthly_rent:
        customer.monthly_rent = reservation.monthly_rent
    if not customer.security_deposit:
        customer.security_deposit = reservation.security_deposit
    customer.save()
    sync_bed(bed)
    for item in documents or []:
        file_data = clean_upload(item.get("file_data"), allow_pdf=True, label="file_data")
        if not file_data:
            continue
        HostelDocument.objects.create(
            business=actor["business"],
            branch=bed.branch,
            customer=customer,
            title=str(item.get("title") or "Reservation document")[:160],
            kind=HostelDocument.Kind.OTHER,
            file_name=str(item.get("file_name") or "")[:180],
            file_data=file_data,
            uploaded_by=actor["user"],
        )
    audit(actor["business"], actor["user"], "reservation.created", f"{reservation.number} · {customer.full_name} · seat {bed.code}", bed.branch, "reservation", reservation.pk)
    notify(actor["business"], "reservation", "New reservation", f"{customer.full_name} reserved seat {bed.code} in room {bed.room.number}.", "/hostel/reservations", bed.branch)
    return reservation


def post_advance(actor, reservation):
    if reservation.advance_posted or reservation.advance_payment <= ZERO:
        return
    record_payment(
        actor,
        customer=reservation.customer,
        amount=reservation.advance_payment,
        payment_type=HostelPayment.Type.ADVANCE,
        method=HostelPayment.Method.CASH,
        payment_date=timezone.localdate(),
        year=reservation.check_in_date.year,
        month=reservation.check_in_date.month,
        notes=f"Advance on {reservation.number}",
        reservation=reservation,
    )
    reservation.advance_posted = True
    reservation.save(update_fields=["advance_posted", "updated_at"])


@transaction.atomic
def check_in(actor, reservation, notes=""):
    ensure_perm(actor, "stays.manage")
    if reservation.status not in (HostelReservation.Status.PENDING, HostelReservation.Status.CONFIRMED):
        raise ValidationError({"detail": "Only a pending or confirmed reservation can be checked in."})
    require_branch(actor, reservation.branch)
    bed = HostelBed.objects.select_for_update().select_related("room", "branch").get(pk=reservation.bed_id)
    assert_bed_free(bed, reservation.check_in_date, reservation.expected_checkout, exclude=reservation.pk)
    if bed.reservations.filter(status=HostelReservation.Status.CHECKED_IN).exclude(pk=reservation.pk).exists():
        raise ValidationError({"bed": "This seat already has a guest checked in."})
    reservation.status = HostelReservation.Status.CHECKED_IN
    reservation.save(update_fields=["status", "updated_at"])
    customer = HostelCustomer.objects.select_for_update().get(pk=reservation.customer_id)
    customer.branch = reservation.branch
    customer.room = reservation.room
    customer.bed = bed
    customer.check_in_date = reservation.check_in_date
    customer.expected_checkout = reservation.expected_checkout
    customer.monthly_rent = reservation.monthly_rent
    if reservation.security_deposit:
        customer.security_deposit = reservation.security_deposit
    customer.status = HostelCustomer.Status.ACTIVE
    if not customer.admission_date:
        customer.admission_date = reservation.check_in_date
    customer.save()
    HostelCheckIn.objects.create(
        business=actor["business"],
        branch=reservation.branch,
        reservation=reservation,
        customer=customer,
        bed=bed,
        checked_in_at=timezone.now(),
        notes=notes or "",
        performed_by=actor["user"],
    )
    sync_bed(bed)
    ensure_month(customer, reservation.check_in_date.year, reservation.check_in_date.month, reservation)
    post_advance(actor, reservation)
    audit(actor["business"], actor["user"], "customer.checked_in", f"{customer.full_name} checked into room {reservation.room.number} seat {bed.code}", reservation.branch, "reservation", reservation.pk)
    notify(actor["business"], "checkin", "Guest checked in", customer.full_name, f"/hostel/customers/{customer.pk}", reservation.branch)
    return reservation


@transaction.atomic
def check_out(actor, reservation, notes=""):
    ensure_perm(actor, "stays.manage")
    if reservation.status != HostelReservation.Status.CHECKED_IN:
        raise ValidationError({"detail": "This guest is not checked in."})
    require_branch(actor, reservation.branch)
    bed = HostelBed.objects.select_for_update().get(pk=reservation.bed_id)
    reservation.status = HostelReservation.Status.COMPLETED
    reservation.save(update_fields=["status", "updated_at"])
    customer = HostelCustomer.objects.select_for_update().get(pk=reservation.customer_id)
    HostelCheckOut.objects.create(
        business=actor["business"],
        branch=reservation.branch,
        reservation=reservation,
        customer=customer,
        bed=bed,
        checked_out_at=timezone.now(),
        notes=notes or "",
        performed_by=actor["user"],
    )
    customer.status = HostelCustomer.Status.CHECKED_OUT
    customer.checkout_date = timezone.localdate()
    customer.room = None
    customer.bed = None
    customer.save()
    sync_bed(bed)
    audit(actor["business"], actor["user"], "customer.checked_out", f"{customer.full_name} checked out of seat {bed.code}", reservation.branch, "reservation", reservation.pk)
    notify(actor["business"], "checkout", "Guest checked out", customer.full_name, f"/hostel/customers/{customer.pk}", reservation.branch)
    return reservation


@transaction.atomic
def cancel_reservation(actor, reservation):
    ensure_perm(actor, "reservations.manage")
    if reservation.status not in (HostelReservation.Status.PENDING, HostelReservation.Status.CONFIRMED):
        raise ValidationError({"detail": "Checked-in stays must be checked out. They cannot be cancelled."})
    require_branch(actor, reservation.branch)
    bed = HostelBed.objects.select_for_update().get(pk=reservation.bed_id)
    reservation.status = HostelReservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    customer = reservation.customer
    if customer.status == HostelCustomer.Status.RESERVED and not customer.reservations.filter(status__in=OPEN_BOOKINGS).exists():
        customer.status = HostelCustomer.Status.INACTIVE
        customer.save(update_fields=["status", "updated_at"])
    sync_bed(bed)
    audit(actor["business"], actor["user"], "reservation.cancelled", reservation.number, reservation.branch, "reservation", reservation.pk)
    return reservation


@transaction.atomic
def extend_stay(actor, reservation, expected_checkout):
    ensure_perm(actor, "stays.manage")
    if reservation.status != HostelReservation.Status.CHECKED_IN:
        raise ValidationError({"detail": "Only a checked-in stay can be extended."})
    require_branch(actor, reservation.branch)
    bed = HostelBed.objects.select_for_update().get(pk=reservation.bed_id)
    assert_bed_free(bed, reservation.check_in_date, expected_checkout, exclude=reservation.pk)
    reservation.expected_checkout = expected_checkout
    reservation.save(update_fields=["expected_checkout", "updated_at"])
    customer = reservation.customer
    customer.expected_checkout = expected_checkout
    customer.save(update_fields=["expected_checkout", "updated_at"])
    audit(actor["business"], actor["user"], "stay.extended", f"{customer.full_name} until {expected_checkout}", reservation.branch, "reservation", reservation.pk)
    return reservation


@transaction.atomic
def change_room(actor, customer, bed, expected_checkout=None):
    ensure_perm(actor, "stays.manage")
    same_customer(actor, customer)
    current = (
        HostelReservation.objects.select_for_update()
        .filter(customer=customer, status=HostelReservation.Status.CHECKED_IN)
        .first()
    )
    if current is None:
        raise ValidationError({"detail": "Check the customer in before changing the room."})
    new_bed = HostelBed.objects.select_for_update().select_related("room", "branch").get(pk=bed.pk)
    require_branch(actor, new_bed.branch)
    end = expected_checkout or current.expected_checkout
    start = timezone.localdate()
    if start < current.check_in_date:
        start = current.check_in_date
    assert_bed_free(new_bed, start, end)
    old_bed = HostelBed.objects.select_for_update().get(pk=current.bed_id)
    current.status = HostelReservation.Status.COMPLETED
    current.save(update_fields=["status", "updated_at"])
    HostelCheckOut.objects.create(
        business=actor["business"],
        branch=current.branch,
        reservation=current,
        customer=customer,
        bed=old_bed,
        checked_out_at=timezone.now(),
        notes="Moved to another seat",
        performed_by=actor["user"],
    )
    moved = HostelReservation.objects.create(
        business=actor["business"],
        branch=new_bed.branch,
        room=new_bed.room,
        bed=new_bed,
        customer=customer,
        number=take_number(actor["business"], "reservation"),
        reservation_date=timezone.localdate(),
        check_in_date=start,
        expected_checkout=end,
        monthly_rent=current.monthly_rent,
        security_deposit=current.security_deposit,
        advance_payment=ZERO,
        advance_posted=True,
        instructions="Room change",
        status=HostelReservation.Status.CHECKED_IN,
        created_by=actor["user"],
    )
    HostelCheckIn.objects.create(
        business=actor["business"],
        branch=new_bed.branch,
        reservation=moved,
        customer=customer,
        bed=new_bed,
        checked_in_at=timezone.now(),
        notes="Room change",
        performed_by=actor["user"],
    )
    customer.branch = new_bed.branch
    customer.room = new_bed.room
    customer.bed = new_bed
    customer.expected_checkout = end
    customer.status = HostelCustomer.Status.ACTIVE
    customer.save()
    sync_bed(old_bed)
    sync_bed(new_bed)
    audit(actor["business"], actor["user"], "seat.assigned", f"{customer.full_name} moved to room {new_bed.room.number} seat {new_bed.code}", new_bed.branch, "reservation", moved.pk)
    return moved


def set_bed_status(actor, bed, status):
    ensure_perm(actor, "seats.manage")
    require_branch(actor, bed.branch)
    allowed = {HostelBed.Status.AVAILABLE, HostelBed.Status.MAINTENANCE, HostelBed.Status.BLOCKED}
    if status not in allowed:
        raise ValidationError({"status": "Occupy or reserve a seat from a reservation."})
    open_exists = bed.reservations.filter(status__in=OPEN_BOOKINGS).exists()
    if open_exists:
        raise ValidationError({"status": "This seat has a booking. Check the guest out or cancel it first."})
    bed.status = status
    bed.save(update_fields=["status", "updated_at"])
    audit(actor["business"], actor["user"], "seat.updated", f"Seat {bed.code} in room {bed.room.number} is {status}", bed.branch, "bed", bed.pk)
    return bed


def open_beds(actor, *, branch_id, check_in, check_out, room_id=None, floor=None):
    if not check_in or not check_out or check_in >= check_out:
        raise ValidationError({"check_out": "Choose a check-in and a later checkout."})
    if actor["role"] != "owner":
        branch_id = actor["branch_id"]
    qs = HostelBed.objects.filter(
        business=actor["business"],
        branch_id=branch_id,
        room__is_deleted=False,
        room__status=HostelRoom.Status.ACTIVE,
        branch__status=HostelBranch.Status.ACTIVE,
    ).exclude(status__in=[HostelBed.Status.MAINTENANCE, HostelBed.Status.BLOCKED])
    if room_id:
        qs = qs.filter(room_id=room_id)
    if floor:
        qs = qs.filter(room__floor=floor)
    busy = HostelReservation.objects.filter(
        bed_id__in=qs.values("id"),
        status__in=OPEN_BOOKINGS,
        check_in_date__lt=check_out,
        expected_checkout__gt=check_in,
    ).values_list("bed_id", flat=True)
    return qs.exclude(id__in=list(busy)).select_related("room", "branch")


def customer_finance(customer):
    months = list(customer.monthly_rents.all())
    payments = [row for row in customer.payments.all() if not row.is_void]
    outstanding = sum((max(ZERO, row.amount_due - row.amount_paid) for row in months), ZERO)
    deposit_paid = sum((row.amount for row in payments if row.payment_type == HostelPayment.Type.DEPOSIT), ZERO)
    registration_paid = sum((row.amount for row in payments if row.payment_type == HostelPayment.Type.REGISTRATION), ZERO)
    deposit_left = max(ZERO, (customer.security_deposit or ZERO) - deposit_paid)
    registration_left = max(ZERO, (customer.registration_fee or ZERO) - registration_paid)
    remaining = max(ZERO, outstanding + deposit_left + registration_left - (customer.credit or ZERO))
    total_paid = sum((row.amount for row in payments), ZERO)
    total_payable = sum((row.amount_due for row in months), ZERO) + (customer.security_deposit or ZERO) + (customer.registration_fee or ZERO)
    last = max(payments, key=lambda row: (row.payment_date, row.created_at), default=None)
    open_months = [row for row in months if row.status != HostelMonthlyRent.Status.PAID]
    next_due = min((row.due_date for row in open_months if row.due_date), default=None)
    return {
        "total_payable": total_payable,
        "total_paid": total_paid,
        "remaining": remaining,
        "credit": customer.credit or ZERO,
        "deposit_paid": deposit_paid,
        "registration_paid": registration_paid,
        "last_payment": last.payment_date.isoformat() if last else None,
        "last_amount": last.amount if last else ZERO,
        "next_due": next_due.isoformat() if next_due else None,
        "paid_months": [f"{calendar.month_name[row.month]} {row.year}" for row in months if row.status == HostelMonthlyRent.Status.PAID],
        "unpaid_months": [f"{calendar.month_name[row.month]} {row.year}" for row in open_months],
        "overdue_months": [f"{calendar.month_name[row.month]} {row.year}" for row in months if row.status == HostelMonthlyRent.Status.OVERDUE],
    }


def finance_dict(customer):
    data = customer_finance(customer)
    for key in ("total_payable", "total_paid", "remaining", "credit", "deposit_paid", "registration_paid", "last_amount"):
        data[key] = str(data[key])
    return data


def assign_permissions(employee):
    HostelEmployeePermission.objects.filter(employee=employee).delete()
    HostelEmployeePermission.objects.bulk_create([
        HostelEmployeePermission(employee=employee, codename=code) for code in codes_for_employee(employee)
    ])


@transaction.atomic
def create_employee(actor, payload):
    ensure_perm(actor, "staff.manage")
    if actor["role"] != "owner":
        payload = {
            **payload,
            "role": HostelEmployee.Role.EMPLOYEE,
            "can_manage_staff": False,
            "can_approve_expenses": False,
            "can_view_reports": False,
            "branch": HostelBranch.objects.get(pk=actor["branch_id"]),
        }
    branch = payload["branch"]
    require_branch(actor, branch)
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if password and not email:
        raise ValidationError({"email": "Add an email if this person will sign in."})
    user = None
    if email:
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": "An account with this email already exists."})
        parts = payload["full_name"].split(" ", 1)
        user = User.objects.create_user(
            email=email,
            password=password or secrets.token_urlsafe(18),
            first_name=parts[0][:80],
            last_name=(parts[1] if len(parts) > 1 else "")[:80],
            phone=payload.get("phone") or "",
            business=actor["business"],
            is_owner=False,
        )
    invite_token = ""
    status = HostelEmployee.Status.ACTIVE
    invite_hash = ""
    if email and not password:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        invite_token = secrets.token_urlsafe(24)
        invite_hash = hashlib.sha256(invite_token.encode()).hexdigest()
        status = HostelEmployee.Status.INVITED
    employee = HostelEmployee.objects.create(
        business=actor["business"],
        branch=branch,
        user=user,
        employee_code=take_number(actor["business"], "employee"),
        full_name=payload["full_name"],
        photo=clean_upload(payload.get("photo") or "", label="photo"),
        email=email,
        phone=payload.get("phone") or "",
        designation=payload.get("designation") or "",
        salary=money(payload.get("salary") or 0),
        joining_date=payload.get("joining_date"),
        role=payload.get("role") or HostelEmployee.Role.EMPLOYEE,
        status=status,
        can_manage_staff=bool(payload.get("can_manage_staff")) and payload.get("role") == HostelEmployee.Role.MANAGER,
        can_approve_expenses=bool(payload.get("can_approve_expenses")) and payload.get("role") == HostelEmployee.Role.MANAGER,
        can_view_reports=bool(payload.get("can_view_reports")),
        invite_hash=invite_hash,
    )
    assign_permissions(employee)
    audit(actor["business"], actor["user"], "employee.created", f"{employee.full_name} · {branch.name}", branch, "employee", employee.pk)
    notify(actor["business"], "employee", "Staff added", employee.full_name, "/hostel/employees", branch)
    return employee, invite_token


def accept_invite(token, password):
    if not token or len(password or "") < 8:
        raise ValidationError({"password": "Use at least 8 characters."})
    digest = hashlib.sha256(token.encode()).hexdigest()
    employee = HostelEmployee.objects.select_related("user").filter(invite_hash=digest, is_deleted=False).first()
    if employee is None or employee.user_id is None:
        raise ValidationError({"token": "This invite link is not valid."})
    employee.user.set_password(password)
    employee.user.is_active = True
    employee.user.save(update_fields=["password", "is_active"])
    employee.invite_hash = ""
    employee.status = HostelEmployee.Status.ACTIVE
    employee.save(update_fields=["invite_hash", "status", "updated_at"])
    return employee


def guard_delete_branch(branch):
    if branch.rooms.filter(is_deleted=False).exists() or branch.customers.filter(is_deleted=False).exists() or branch.payments.filter(is_void=False).exists():
        raise ValidationError({"detail": "This branch has rooms or records. Deactivate it instead of deleting it."})


def period_bounds(params, today=None):
    today = today or timezone.localdate()
    start = params.get("date_from") or None
    end = params.get("date_to") or None
    year = params.get("year")
    month = params.get("month")
    if start or end:
        return start, end, "range"
    if year and month:
        year, month = int(year), int(month)
        return date(year, month, 1), date(year, month, month_end(year, month)), "month"
    if year:
        year = int(year)
        return date(year, 1, 1), date(year, 12, 31), "year"
    return date(today.year, today.month, 1), today, "month"


def scoped_payments(actor, params):
    qs = HostelPayment.objects.filter(business=actor["business"], is_void=False)
    if actor["role"] != "owner":
        qs = qs.filter(branch_id=actor["branch_id"])
    elif params.get("branch"):
        qs = qs.filter(branch_id=params.get("branch"))
    if params.get("customer"):
        qs = qs.filter(customer_id=params.get("customer"))
    if params.get("employee"):
        employee = HostelEmployee.objects.filter(business=actor["business"], pk=params.get("employee")).first()
        if employee and employee.user_id:
            qs = qs.filter(received_by_id=employee.user_id)
        else:
            qs = qs.none()
    if actor["role"] == "employee":
        # Owner dashboard totals stay complete. An employee dashboard shows their own collections
        # unless they are looking at a customer profile through another endpoint.
        if params.get("scope") != "branch":
            qs = qs.filter(received_by=actor["user"])
    return qs


def dashboard(actor, params):
    today = timezone.localdate()
    start, end, _kind = period_bounds(params, today)
    business = actor["business"]
    branch_id = actor["branch_id"] if actor["role"] != "owner" else params.get("branch") or None
    beds = HostelBed.objects.filter(business=business, room__is_deleted=False)
    rooms = HostelRoom.objects.filter(business=business, is_deleted=False)
    customers = HostelCustomer.objects.filter(business=business, is_deleted=False)
    branches = HostelBranch.objects.filter(business=business, is_deleted=False)
    if branch_id:
        beds = beds.filter(branch_id=branch_id)
        rooms = rooms.filter(branch_id=branch_id)
        customers = customers.filter(branch_id=branch_id)
        branches = branches.filter(pk=branch_id)
    payments = scoped_payments(actor, {**params, "branch": branch_id} if branch_id else params)
    period_payments = payments.filter(payment_date__gte=start, payment_date__lte=end)
    all_collected = payments.aggregate(total=Sum("amount"))["total"] or ZERO
    period_collected = period_payments.aggregate(total=Sum("amount"))["total"] or ZERO
    expenses = HostelExpense.objects.filter(business=business, expense_date__gte=start, expense_date__lte=end).exclude(approval=HostelExpense.Approval.REJECTED)
    maintenance = HostelMaintenance.objects.filter(business=business)
    if branch_id:
        expenses = expenses.filter(branch_id=branch_id)
        maintenance = maintenance.filter(branch_id=branch_id)
    if actor["role"] == "employee":
        expenses = expenses.none()
        maintenance = maintenance.filter(reported_by=actor["user"])
    expense_total = expenses.aggregate(total=Sum("amount"))["total"] or ZERO
    maintenance_cost = maintenance.filter(status=HostelMaintenance.Status.COMPLETED).aggregate(total=Sum("actual_cost"))["total"] or ZERO
    bills = HostelMonthlyRent.objects.filter(business=business)
    if branch_id:
        bills = bills.filter(branch_id=branch_id)
    status_filter = params.get("payment_status")
    if status_filter:
        bills = bills.filter(status=status_filter)
    bill_rows = list(bills)
    pending_amount = sum((max(ZERO, row.amount_due - row.amount_paid) for row in bill_rows if row.status != HostelMonthlyRent.Status.PAID), ZERO)
    overdue_amount = sum((max(ZERO, row.amount_due - row.amount_paid) for row in bill_rows if row.status == HostelMonthlyRent.Status.OVERDUE), ZERO)
    show_finance = actor["role"] != "employee"
    seat_counts = {
        "total": beds.count(),
        "occupied": beds.filter(status=HostelBed.Status.OCCUPIED).count(),
        "available": beds.filter(status=HostelBed.Status.AVAILABLE).count(),
        "reserved": beds.filter(status=HostelBed.Status.RESERVED).count(),
        "maintenance": beds.filter(status=HostelBed.Status.MAINTENANCE).count(),
    }
    months = []
    cursor_year, cursor_month = today.year, today.month
    for _ in range(6):
        months.append((cursor_year, cursor_month))
        cursor_month -= 1
        if cursor_month == 0:
            cursor_month = 12
            cursor_year -= 1
    months.reverse()
    revenue_points = []
    expense_points = []
    for year, month in months:
        label = calendar.month_abbr[month]
        revenue_points.append({
            "label": label,
            "value": float(payments.filter(payment_date__year=year, payment_date__month=month).aggregate(total=Sum("amount"))["total"] or 0),
        })
        if show_finance:
            expense_points.append({
                "label": label,
                "value": float(HostelExpense.objects.filter(
                    business=business, expense_date__year=year, expense_date__month=month,
                    **({"branch_id": branch_id} if branch_id else {}),
                ).exclude(approval=HostelExpense.Approval.REJECTED).aggregate(total=Sum("amount"))["total"] or 0),
            })
    comparison = []
    if show_finance and actor["role"] == "owner":
        for branch in HostelBranch.objects.filter(business=business, is_deleted=False):
            collected = HostelPayment.objects.filter(business=business, branch=branch, is_void=False, payment_date__gte=start, payment_date__lte=end).aggregate(total=Sum("amount"))["total"] or ZERO
            spent = HostelExpense.objects.filter(branch=branch, expense_date__gte=start, expense_date__lte=end).exclude(approval=HostelExpense.Approval.REJECTED).aggregate(total=Sum("amount"))["total"] or ZERO
            seat_total = branch.beds.filter(room__is_deleted=False).count()
            occupied = branch.beds.filter(room__is_deleted=False, status=HostelBed.Status.OCCUPIED).count()
            comparison.append({
                "id": str(branch.id),
                "name": branch.name,
                "revenue": str(collected),
                "expenses": str(spent),
                "profit": str(collected - spent),
                "occupancy": round((occupied / seat_total) * 100) if seat_total else 0,
                "seats": seat_total,
                "occupied": occupied,
            })
    alerts = []
    if overdue_amount > ZERO:
        alerts.append({"kind": "overdue", "title": "Overdue rent", "body": f"Rs {overdue_amount} is overdue.", "href": "/hostel/payments"})
    soon = today + timedelta(days=5)
    upcoming = bills.filter(status__in=[HostelMonthlyRent.Status.UNPAID, HostelMonthlyRent.Status.PARTIAL], due_date__gte=today, due_date__lte=soon).count()
    if upcoming:
        alerts.append({"kind": "due", "title": "Rent due soon", "body": f"{upcoming} bills are due within 5 days.", "href": "/hostel/payments"})
    checkout_soon = customers.filter(status=HostelCustomer.Status.ACTIVE, expected_checkout__gte=today, expected_checkout__lte=today + timedelta(days=7)).count()
    if checkout_soon:
        alerts.append({"kind": "leaving", "title": "Stays ending soon", "body": f"{checkout_soon} customers are due to leave within 7 days.", "href": "/hostel/customers"})
    pending_res = HostelReservation.objects.filter(business=business, status=HostelReservation.Status.PENDING)
    if branch_id:
        pending_res = pending_res.filter(branch_id=branch_id)
    if pending_res.exists():
        alerts.append({"kind": "reservation", "title": "Reservations waiting", "body": f"{pending_res.count()} reservations are pending.", "href": "/hostel/reservations"})
    if show_finance:
        waiting = HostelExpense.objects.filter(business=business, approval=HostelExpense.Approval.PENDING)
        if branch_id:
            waiting = waiting.filter(branch_id=branch_id)
        if waiting.exists():
            alerts.append({"kind": "expense", "title": "Expenses to approve", "body": f"{waiting.count()} expenses are waiting.", "href": "/hostel/expenses"})
    open_jobs = HostelMaintenance.objects.filter(business=business, status__in=[HostelMaintenance.Status.PENDING, HostelMaintenance.Status.IN_PROGRESS])
    if branch_id:
        open_jobs = open_jobs.filter(branch_id=branch_id)
    if actor["role"] == "employee":
        open_jobs = open_jobs.filter(reported_by=actor["user"])
    if open_jobs.exists():
        alerts.append({"kind": "maintenance", "title": "Open maintenance", "body": f"{open_jobs.count()} requests are open.", "href": "/hostel/expenses"})
    recent = [
        {
            "id": str(row.id),
            "receipt_no": row.receipt_no,
            "customer": row.customer.full_name,
            "amount": str(row.amount),
            "date": row.payment_date.isoformat(),
            "method": row.method,
            "type": row.payment_type,
            "branch": row.branch.name if row.branch_id else "",
            "received_by": row.received_by.full_name if row.received_by_id else "",
        }
        for row in period_payments.select_related("customer", "branch", "received_by").order_by("-payment_date", "-created_at")[:8]
    ]
    return {
        "role": actor["role"],
        "branch_id": str(actor["branch_id"]) if actor["branch_id"] else None,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "show_finance": show_finance,
        "stats": {
            "branches": branches.count() if actor["role"] == "owner" and not params.get("branch") else branches.count(),
            "rooms": rooms.count(),
            "seats": seat_counts["total"],
            "occupied": seat_counts["occupied"],
            "available": seat_counts["available"],
            "reserved": seat_counts["reserved"],
            "maintenance_seats": seat_counts["maintenance"],
            "customers": customers.count(),
            "active_customers": customers.filter(status=HostelCustomer.Status.ACTIVE).count(),
            "month_revenue": str(period_collected),
            "collected": str(all_collected) if show_finance or actor["role"] == "employee" else str(period_collected),
            "pending": str(pending_amount),
            "overdue": str(overdue_amount),
            "expenses": str(expense_total) if show_finance else None,
            "maintenance_cost": str(maintenance_cost) if show_finance else None,
            "profit": str(period_collected - expense_total) if show_finance else None,
        },
        "charts": {
            "revenue": revenue_points,
            "expenses": expense_points,
            "collections": revenue_points,
            "occupancy": seat_counts,
            "branches": comparison,
        },
        "alerts": alerts,
        "recent_payments": recent,
    }


def search_hostel(actor, query):
    query = (query or "").strip()
    if len(query) < 2:
        return {"customers": [], "reservations": [], "payments": []}
    customers = HostelCustomer.objects.filter(business=actor["business"], is_deleted=False)
    reservations = HostelReservation.objects.filter(business=actor["business"])
    payments = HostelPayment.objects.filter(business=actor["business"], is_void=False)
    if actor["role"] != "owner":
        customers = customers.filter(branch_id=actor["branch_id"])
        reservations = reservations.filter(branch_id=actor["branch_id"])
        payments = payments.filter(branch_id=actor["branch_id"])
    if actor["role"] == "employee":
        payments = payments.filter(received_by=actor["user"])
    customers = customers.filter(
        Q(full_name__icontains=query) | Q(mobile__icontains=query) | Q(whatsapp__icontains=query) | Q(cnic__icontains=query) | Q(bed__code__icontains=query) | Q(room__number__icontains=query)
    )[:8]
    reservations = reservations.filter(Q(number__icontains=query) | Q(customer__full_name__icontains=query) | Q(bed__code__icontains=query) | Q(room__number__icontains=query))[:8]
    payments = payments.filter(Q(receipt_no__icontains=query) | Q(transaction_id__icontains=query) | Q(customer__full_name__icontains=query))[:8]
    return {
        "customers": [{"id": str(row.id), "label": row.full_name, "hint": row.mobile or row.cnic, "href": f"/hostel/customers/{row.id}"} for row in customers],
        "reservations": [{"id": str(row.id), "label": row.number, "hint": row.customer.full_name, "href": "/hostel/reservations"} for row in reservations.select_related("customer")],
        "payments": [{"id": str(row.id), "label": row.receipt_no, "hint": row.customer.full_name, "href": "/hostel/payments/history"} for row in payments.select_related("customer")],
    }


def build_report(actor, kind, params):
    if actor["role"] == "owner":
        ensure_perm(actor, "reports.owner")
    else:
        ensure_perm(actor, "reports.branch")
    start, end, _kind = period_bounds(params)
    business = actor["business"]
    branch_id = actor["branch_id"] if actor["role"] != "owner" else params.get("branch") or None
    sheet = settings_for(business)
    title = sheet.display_name or business.name
    base = {"hostel": title, "logo": sheet.logo, "period": {"from": start.isoformat(), "to": end.isoformat()}, "kind": kind}

    def branch_qs(model_qs):
        if branch_id:
            return model_qs.filter(branch_id=branch_id)
        return model_qs

    if kind == "occupancy":
        rooms = branch_qs(HostelRoom.objects.filter(business=business, is_deleted=False)).select_related("branch")
        rows = []
        for room in rooms:
            beds = list(room.beds.all())
            rows.append({
                "branch": room.branch.name,
                "room": room.number,
                "floor": room.floor,
                "seats": len(beds),
                "occupied": sum(1 for bed in beds if bed.status == HostelBed.Status.OCCUPIED),
                "available": sum(1 for bed in beds if bed.status == HostelBed.Status.AVAILABLE),
                "reserved": sum(1 for bed in beds if bed.status == HostelBed.Status.RESERVED),
                "maintenance": sum(1 for bed in beds if bed.status == HostelBed.Status.MAINTENANCE),
            })
        return {**base, "title": "Branch occupancy", "rows": rows}
    if kind == "seats":
        beds = branch_qs(HostelBed.objects.filter(business=business, room__is_deleted=False, status=HostelBed.Status.AVAILABLE)).select_related("branch", "room")
        return {**base, "title": "Available seats", "rows": [{"branch": bed.branch.name, "room": bed.room.number, "floor": bed.room.floor, "seat": bed.code, "rent": str(bed.room.monthly_rent)} for bed in beds]}
    if kind == "collections":
        payments = branch_qs(HostelPayment.objects.filter(business=business, is_void=False, payment_date__gte=start, payment_date__lte=end)).select_related("customer", "branch", "received_by")
        rows = [{"date": row.payment_date.isoformat(), "receipt": row.receipt_no, "customer": row.customer.full_name, "branch": row.branch.name if row.branch_id else "", "type": row.payment_type, "method": row.method, "amount": str(row.amount), "employee": row.received_by.full_name if row.received_by_id else ""} for row in payments]
        total = sum((Decimal(row["amount"]) for row in rows), ZERO)
        return {**base, "title": "Monthly collection", "rows": rows, "total": str(total)}
    if kind == "outstanding":
        bills = branch_qs(HostelMonthlyRent.objects.filter(business=business).exclude(status=HostelMonthlyRent.Status.PAID)).select_related("customer", "branch")
        rows = [{"customer": row.customer.full_name, "branch": row.branch.name if row.branch_id else "", "month": f"{calendar.month_name[row.month]} {row.year}", "due": str(row.amount_due), "paid": str(row.amount_paid), "balance": str(max(ZERO, row.amount_due - row.amount_paid)), "status": row.status} for row in bills]
        return {**base, "title": "Outstanding payments", "rows": rows, "total": str(sum((Decimal(row["balance"]) for row in rows), ZERO))}
    if kind == "customers":
        people = branch_qs(HostelCustomer.objects.filter(business=business, is_deleted=False)).select_related("branch", "room", "bed")
        return {**base, "title": "Customer list", "rows": [{"name": row.full_name, "mobile": row.mobile, "cnic": row.cnic, "branch": row.branch.name if row.branch_id else "", "room": row.room.number if row.room_id else "", "seat": row.bed.code if row.bed_id else "", "status": row.status, "rent": str(row.monthly_rent)} for row in people]}
    if kind == "employees":
        if actor["role"] == "employee":
            raise PermissionDenied("Employee collection reports are for the owner and branch manager.")
        staff = branch_qs(HostelEmployee.objects.filter(business=business, is_deleted=False)).select_related("branch", "user")
        rows = []
        for person in staff:
            collected = HostelPayment.objects.filter(business=business, is_void=False, received_by=person.user, payment_date__gte=start, payment_date__lte=end)
            rows.append({"name": person.full_name, "branch": person.branch.name, "transactions": collected.count(), "collected": str(collected.aggregate(total=Sum("amount"))["total"] or ZERO)})
        return {**base, "title": "Employee collection", "rows": rows}
    if kind == "expenses":
        if actor["role"] == "employee":
            raise PermissionDenied("Expense reports are for the owner and branch manager.")
        rows_qs = branch_qs(HostelExpense.objects.filter(business=business, expense_date__gte=start, expense_date__lte=end)).select_related("branch")
        rows = [{"date": row.expense_date.isoformat(), "title": row.title, "branch": row.branch.name, "category": row.category, "amount": str(row.amount), "approval": row.approval} for row in rows_qs]
        return {**base, "title": "Expense report", "rows": rows, "total": str(sum((Decimal(row["amount"]) for row in rows if row["approval"] != "rejected"), ZERO))}
    if kind == "maintenance":
        rows_qs = branch_qs(HostelMaintenance.objects.filter(business=business)).select_related("branch", "room")
        return {**base, "title": "Maintenance report", "rows": [{"title": row.title, "branch": row.branch.name, "room": row.room.number if row.room_id else "", "priority": row.priority, "status": row.status, "estimated": str(row.estimated_cost), "actual": str(row.actual_cost)} for row in rows_qs]}
    if kind == "branch":
        branch = branches_for_report(actor, branch_id)
        payload = dashboard(actor, {"branch": str(branch.id), "date_from": start.isoformat(), "date_to": end.isoformat(), "scope": "branch"})
        return {**base, "title": f"Branch report · {branch.name}", "branch": {"name": branch.name, "code": branch.code, "address": branch.address, "phone": branch.phone}, "stats": payload["stats"], "rows": payload["charts"]["branches"]}
    raise ValidationError({"type": "Unknown report."})


def branches_for_report(actor, branch_id):
    if branch_id:
        branch = HostelBranch.objects.filter(business=actor["business"], pk=branch_id, is_deleted=False).first()
    else:
        branch = HostelBranch.objects.filter(business=actor["business"], is_deleted=False).first()
    if branch is None:
        raise ValidationError({"branch": "Add a branch before running this report."})
    if actor["role"] != "owner" and branch.id != actor["branch_id"]:
        raise PermissionDenied("You can only report on your branch.")
    return branch


def refresh_overdue():
    today = timezone.localdate()
    qs = HostelMonthlyRent.objects.filter(due_date__lt=today).exclude(status=HostelMonthlyRent.Status.PAID)
    for bill in qs.iterator():
        status = bill_status(bill, today)
        if bill.status != status:
            HostelMonthlyRent.objects.filter(pk=bill.pk).update(status=status)
