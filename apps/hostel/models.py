from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class HostelSettings(TimeStampedModel):
    business = models.OneToOneField("businesses.Business", on_delete=models.CASCADE, related_name="hostel_settings")
    display_name = models.CharField(max_length=160, blank=True)
    tagline = models.CharField(max_length=180, blank=True)
    logo = models.TextField(blank=True)
    due_day = models.PositiveSmallIntegerField(default=5)
    late_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    receipt_prefix = models.CharField(max_length=8, default="HST")
    next_receipt = models.PositiveIntegerField(default=1)
    next_reservation = models.PositiveIntegerField(default=1)
    next_employee = models.PositiveIntegerField(default=1)
    next_invoice = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.display_name or "Hostel settings"


class HostelBranch(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_branches")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    manager_name = models.CharField(max_length=160, blank=True)
    floors = models.PositiveSmallIntegerField(default=1)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    opening_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    image = models.TextField(blank=True)
    manager = models.OneToOneField(
        "hostel.HostelEmployee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_branch",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["business", "code"], name="hostel_branch_code"),
        ]
        indexes = [models.Index(fields=["business", "status"])]

    def __str__(self):
        return self.name


class HostelRoom(TimeStampedModel):
    class RoomType(models.TextChoices):
        SINGLE = "single", "Single Sharing"
        DOUBLE = "double", "Double Sharing"
        TRIPLE = "triple", "Triple Sharing"
        FOUR = "four", "Four Sharing"
        SIX = "six", "Six Sharing"
        CUSTOM = "custom", "Custom Capacity"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "Maintenance"
        INACTIVE = "inactive", "Inactive"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_rooms")
    branch = models.ForeignKey(HostelBranch, on_delete=models.CASCADE, related_name="rooms")
    number = models.CharField(max_length=20)
    floor = models.PositiveSmallIntegerField(default=1)
    room_type = models.CharField(max_length=12, choices=RoomType.choices, default=RoomType.DOUBLE)
    capacity = models.PositiveSmallIntegerField(default=2)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    mattress_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    attached_bathroom = models.BooleanField(default=False)
    ac = models.BooleanField(default=False)
    wifi = models.BooleanField(default=True)
    facilities = models.CharField(max_length=255, blank=True)
    image = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    is_deleted = models.BooleanField(default=False)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["floor", "number"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "number"], name="hostel_room_number"),
        ]
        indexes = [models.Index(fields=["business", "branch", "floor"])]

    def __str__(self):
        return f"Room {self.number}"


class HostelBed(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"
        BLOCKED = "blocked", "Blocked"

    class Furnishing(models.TextChoices):
        BED = "bed", "Bed"
        MATTRESS = "mattress", "Mattress"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_beds")
    branch = models.ForeignKey(HostelBranch, on_delete=models.CASCADE, related_name="beds")
    room = models.ForeignKey(HostelRoom, on_delete=models.CASCADE, related_name="beds")
    code = models.CharField(max_length=12)
    furnishing = models.CharField(max_length=12, choices=Furnishing.choices, default=Furnishing.BED)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["room", "code"], name="hostel_bed_code"),
        ]
        indexes = [models.Index(fields=["business", "branch", "status"])]

    def __str__(self):
        return f"{self.room.number}-{self.code}"


class HostelCustomer(TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RESERVED = "reserved", "Reserved"
        CHECKED_OUT = "checked_out", "Checked out"
        INACTIVE = "inactive", "Inactive"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_customers")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="customers", null=True, blank=True)
    room = models.ForeignKey(HostelRoom, on_delete=models.SET_NULL, related_name="occupants", null=True, blank=True)
    bed = models.ForeignKey(HostelBed, on_delete=models.SET_NULL, related_name="occupants", null=True, blank=True)
    full_name = models.CharField(max_length=160)
    father_name = models.CharField(max_length=160, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=12, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    permanent_address = models.TextField(blank=True)
    current_address = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=80, blank=True)
    guardian_name = models.CharField(max_length=160, blank=True)
    guardian_contact = models.CharField(max_length=30, blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    photo = models.TextField(blank=True)
    cnic_front = models.TextField(blank=True)
    cnic_back = models.TextField(blank=True)
    admission_date = models.DateField(null=True, blank=True)
    check_in_date = models.DateField(null=True, blank=True)
    expected_checkout = models.DateField(null=True, blank=True)
    checkout_date = models.DateField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registration_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_customers_created")
    is_deleted = models.BooleanField(default=False)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "mobile"]),
            models.Index(fields=["business", "cnic"]),
        ]

    def __str__(self):
        return self.full_name


class HostelDocument(TimeStampedModel):
    class Kind(models.TextChoices):
        PHOTO = "photo", "Photo"
        CNIC_FRONT = "cnic_front", "CNIC front"
        CNIC_BACK = "cnic_back", "CNIC back"
        PAYMENT = "payment", "Payment"
        OTHER = "other", "Other"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_documents")
    branch = models.ForeignKey(HostelBranch, on_delete=models.CASCADE, related_name="documents", null=True, blank=True)
    customer = models.ForeignKey(HostelCustomer, on_delete=models.CASCADE, related_name="documents", null=True, blank=True)
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.OTHER)
    file_name = models.CharField(max_length=180, blank=True)
    file_data = models.TextField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_documents_uploaded")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "customer"])]


class HostelReservation(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked in"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_reservations")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="reservations")
    room = models.ForeignKey(HostelRoom, on_delete=models.PROTECT, related_name="reservations")
    bed = models.ForeignKey(HostelBed, on_delete=models.PROTECT, related_name="reservations")
    customer = models.ForeignKey(HostelCustomer, on_delete=models.PROTECT, related_name="reservations")
    number = models.CharField(max_length=20)
    reservation_date = models.DateField()
    check_in_date = models.DateField()
    expected_checkout = models.DateField()
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_posted = models.BooleanField(default=False)
    instructions = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_reservations_created")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-reservation_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="hostel_reservation_no"),
        ]
        indexes = [
            models.Index(fields=["bed", "status"]),
            models.Index(fields=["business", "status"]),
            models.Index(fields=["check_in_date", "expected_checkout"]),
        ]


class HostelCheckIn(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_checkins")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="checkins")
    reservation = models.ForeignKey(HostelReservation, on_delete=models.CASCADE, related_name="checkins")
    customer = models.ForeignKey(HostelCustomer, on_delete=models.CASCADE, related_name="checkins")
    bed = models.ForeignKey(HostelBed, on_delete=models.PROTECT, related_name="checkins")
    checked_in_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_checkins_done")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-checked_in_at"]


class HostelCheckOut(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_checkouts")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="checkouts")
    reservation = models.ForeignKey(HostelReservation, on_delete=models.CASCADE, related_name="checkouts")
    customer = models.ForeignKey(HostelCustomer, on_delete=models.CASCADE, related_name="checkouts")
    bed = models.ForeignKey(HostelBed, on_delete=models.PROTECT, related_name="checkouts")
    checked_out_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_checkouts_done")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-checked_out_at"]


class HostelMonthlyRent(TimeStampedModel):
    class Status(models.TextChoices):
        PAID = "paid", "Paid"
        PARTIAL = "partial", "Partially paid"
        UNPAID = "unpaid", "Unpaid"
        OVERDUE = "overdue", "Overdue"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_monthly_rents")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="monthly_rents", null=True, blank=True)
    customer = models.ForeignKey(HostelCustomer, on_delete=models.CASCADE, related_name="monthly_rents")
    reservation = models.ForeignKey(HostelReservation, on_delete=models.SET_NULL, null=True, blank=True, related_name="monthly_rents")
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extra_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNPAID)
    invoice_number = models.CharField(max_length=20, blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["customer", "year", "month"], name="hostel_month_bill"),
        ]
        indexes = [models.Index(fields=["business", "status", "due_date"])]


class HostelInvoice(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_invoices")
    customer = models.ForeignKey(HostelCustomer, on_delete=models.CASCADE, related_name="invoices")
    monthly_rent = models.OneToOneField(HostelMonthlyRent, on_delete=models.CASCADE, related_name="invoice")
    number = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    objects = BusinessScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="hostel_invoice_no"),
        ]


class HostelPayment(TimeStampedModel):
    class Type(models.TextChoices):
        RENT = "rent", "Monthly rent"
        DEPOSIT = "deposit", "Security deposit"
        ADVANCE = "advance", "Advance payment"
        REGISTRATION = "registration", "Registration fee"
        ELECTRICITY = "electricity", "Electricity charges"
        GAS = "gas", "Gas charges"
        LAUNDRY = "laundry", "Laundry charges"
        INTERNET = "internet", "Internet charges"
        OTHER = "other", "Other charges"

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        JAZZCASH = "jazzcash", "JazzCash"
        EASYPAISA = "easypaisa", "EasyPaisa"
        ONLINE = "online", "Online payment"
        OTHER = "other", "Other"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_payments")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    customer = models.ForeignKey(HostelCustomer, on_delete=models.PROTECT, related_name="payments")
    reservation = models.ForeignKey(HostelReservation, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    room = models.ForeignKey(HostelRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    bed = models.ForeignKey(HostelBed, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    monthly_rent = models.ForeignKey(HostelMonthlyRent, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    receipt_no = models.CharField(max_length=20)
    payment_type = models.CharField(max_length=16, choices=Type.choices, default=Type.RENT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    period_year = models.PositiveSmallIntegerField(null=True, blank=True)
    period_month = models.PositiveSmallIntegerField(null=True, blank=True)
    method = models.CharField(max_length=12, choices=Method.choices, default=Method.CASH)
    transaction_id = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    receipt_image = models.TextField(blank=True)
    screenshot = models.TextField(blank=True)
    applications = models.JSONField(default=list, blank=True)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_payments_received")
    is_void = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_payments_voided")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "receipt_no"], name="hostel_receipt_no"),
        ]
        indexes = [
            models.Index(fields=["business", "payment_date"]),
            models.Index(fields=["customer", "payment_date"]),
            models.Index(fields=["received_by", "payment_date"]),
        ]


class HostelExpense(TimeStampedModel):
    class Category(models.TextChoices):
        ELECTRICITY = "electricity", "Electricity"
        GAS = "gas", "Gas"
        WATER = "water", "Water"
        INTERNET = "internet", "Internet"
        SALARY = "salary", "Staff salaries"
        CLEANING = "cleaning", "Cleaning"
        REPAIRS = "repairs", "Repairs"
        FURNITURE = "furniture", "Furniture"
        MAINTENANCE = "maintenance", "Maintenance"
        SECURITY = "security", "Security"
        FOOD = "food", "Food"
        OTHER = "other", "Other expenses"

    class Approval(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_expenses")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="expenses")
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    description = models.TextField(blank=True)
    method = models.CharField(max_length=12, choices=HostelPayment.Method.choices, default=HostelPayment.Method.CASH)
    receipt_image = models.TextField(blank=True)
    approval = models.CharField(max_length=12, choices=Approval.choices, default=Approval.PENDING)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_expenses_recorded")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_expenses_approved")
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        indexes = [models.Index(fields=["business", "branch", "expense_date"])]


class HostelMaintenance(TimeStampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_maintenance")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="maintenance_requests")
    room = models.ForeignKey(HostelRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_requests")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    images = models.JSONField(default=list, blank=True)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_maintenance_reported")
    assigned_worker = models.CharField(max_length=160, blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    completion_date = models.DateField(null=True, blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "branch", "status"])]


class HostelEmployee(TimeStampedModel):
    class Role(models.TextChoices):
        MANAGER = "manager", "Branch manager"
        EMPLOYEE = "employee", "Branch employee"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INVITED = "invited", "Invited"
        INACTIVE = "inactive", "Inactive"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_employees")
    branch = models.ForeignKey(HostelBranch, on_delete=models.PROTECT, related_name="employees")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hostel_employee", null=True, blank=True)
    employee_code = models.CharField(max_length=20)
    full_name = models.CharField(max_length=160)
    photo = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    designation = models.CharField(max_length=80, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    joining_date = models.DateField(null=True, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.EMPLOYEE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    can_manage_staff = models.BooleanField(default=False)
    can_approve_expenses = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)
    invite_hash = models.CharField(max_length=64, blank=True, db_index=True)
    is_deleted = models.BooleanField(default=False)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(fields=["business", "employee_code"], name="hostel_employee_code"),
        ]
        indexes = [models.Index(fields=["business", "branch", "status"])]

    def __str__(self):
        return self.full_name


class HostelEmployeePermission(TimeStampedModel):
    employee = models.ForeignKey(HostelEmployee, on_delete=models.CASCADE, related_name="permissions")
    codename = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["employee", "codename"], name="hostel_employee_perm"),
        ]


class HostelNotification(TimeStampedModel):
    class Audience(models.TextChoices):
        OWNER = "owner", "Owner"
        BRANCH = "branch", "Branch"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_notifications")
    branch = models.ForeignKey(HostelBranch, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hostel_notifications", null=True, blank=True)
    audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.OWNER)
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=400, blank=True)
    href = models.CharField(max_length=180, blank=True)
    is_read = models.BooleanField(default=False)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "is_read"])]


class HostelAuditLog(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="hostel_audit_logs")
    branch = models.ForeignKey(HostelBranch, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hostel_audit_logs")
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=255)
    entity = models.CharField(max_length=40, blank=True)
    entity_id = models.CharField(max_length=40, blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "action"])]
