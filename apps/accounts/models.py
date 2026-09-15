import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.models import TimeStampedModel


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    module = models.CharField(max_length=40)
    module_label = models.CharField(max_length=80)

    class Meta:
        ordering = ["module", "codename"]

    def __str__(self):
        return self.codename


class Role(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="roles",
    )
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.business.name} / {self.name}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_platform_admin", True)
        extra.setdefault("is_owner", False)
        extra.setdefault("business", None)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
    )
    default_branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.SET_NULL,
        related_name="default_users",
        null=True,
        blank=True,
    )
    branches = models.ManyToManyField(
        "businesses.Branch",
        through="UserBranch",
        related_name="assigned_users",
        blank=True,
    )
    is_owner = models.BooleanField(default=False)
    is_platform_admin = models.BooleanField(
        default=False,
        help_text="Software owner who can see every business on the platform.",
    )
    pin_hash = models.CharField(max_length=128, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name", "email"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    def permission_codes(self) -> set[str]:
        if self.is_owner or self.is_superuser:
            from apps.core.catalog import PERMISSION_CATALOG

            return {item.codename for item in PERMISSION_CATALOG}
        if not self.role_id:
            return set()
        return set(self.role.permissions.values_list("codename", flat=True))

    def has_module_permission(self, codename: str) -> bool:
        if not self.is_active:
            return False
        if self.is_owner or self.is_superuser:
            return True
        return codename in self.permission_codes()


class UserBranch(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="branch_links")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.CASCADE,
        related_name="user_links",
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "branch")
