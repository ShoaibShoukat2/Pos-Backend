from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.helpers import cashier_role_for, is_cashier_user
from apps.accounts.models import Permission, Role
from apps.businesses.models import Business, BusinessType
from apps.core.services import seed_business_defaults

User = get_user_model()


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ("id", "codename", "name", "module", "module_label")


class RoleSerializer(serializers.ModelSerializer):
    permission_ids = serializers.PrimaryKeyRelatedField(
        source="permissions",
        many=True,
        queryset=Permission.objects.all(),
        required=False,
    )
    permissions = PermissionSerializer(many=True, read_only=True)
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "name",
            "description",
            "is_system",
            "permissions",
            "permission_ids",
            "user_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("is_system", "created_at", "updated_at")

    def validate_name(self, value):
        business = self.context["request"].user.business
        qs = Role.objects.filter(business=business, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    default_branch_name = serializers.CharField(source="default_branch.name", read_only=True)
    branch_ids = serializers.PrimaryKeyRelatedField(
        source="branches",
        many=True,
        required=False,
        read_only=True,
    )
    assigned_branch_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
    )
    permissions = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "is_active",
            "is_owner",
            "role",
            "role_name",
            "default_branch",
            "default_branch_name",
            "branch_ids",
            "assigned_branch_ids",
            "permissions",
            "password",
            "date_joined",
        )
        read_only_fields = ("is_owner", "date_joined", "full_name")

    def get_permissions(self, obj):
        return sorted(obj.permission_codes())

    def validate_role(self, role):
        request = self.context["request"]
        if role and role.business_id != request.user.business_id:
            raise serializers.ValidationError("Role does not belong to this business.")
        return role

    def validate_default_branch(self, branch):
        request = self.context["request"]
        if branch and branch.business_id != request.user.business_id:
            raise serializers.ValidationError("Branch does not belong to this business.")
        return branch

    def _apply_branches(self, user, branch_ids):
        from apps.businesses.models import Branch

        if branch_ids is None:
            return
        branches = list(
            Branch.objects.filter(business=user.business, id__in=branch_ids)
        )
        user.branches.set(branches)
        if user.default_branch_id and user.default_branch_id not in {b.id for b in branches}:
            user.default_branch = branches[0] if branches else None
            user.save(update_fields=["default_branch"])

    def create(self, validated):
        request = self.context["request"]
        password = validated.pop("password", None)
        branch_ids = validated.pop("assigned_branch_ids", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})
        user = User(**validated)
        user.business = request.user.business
        user.set_password(password)
        user.save()
        self._apply_branches(user, branch_ids)
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        branch_ids = validated.pop("assigned_branch_ids", None)
        if instance.is_owner:
            validated.pop("is_active", None)
        for attr, value in validated.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        self._apply_branches(instance, branch_ids)
        return instance


class MeSerializer(UserSerializer):
    business_id = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()
    business_type = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField(read_only=True)
    is_cashier = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "business_id",
            "business_name",
            "business_type",
            "is_platform_admin",
            "is_cashier",
        )

    def get_is_cashier(self, obj):
        return is_cashier_user(obj)

    def get_business_id(self, obj):
        return str(obj.business_id) if obj.business_id else None

    def get_business_name(self, obj):
        return obj.business.name if obj.business_id else None

    def get_business_type(self, obj):
        return obj.business.business_type if obj.business_id else None


class RegisterSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=160)
    business_type = serializers.ChoiceField(
        choices=BusinessType.choices,
        default=BusinessType.GENERAL,
    )
    city = serializers.CharField(max_length=80, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    @transaction.atomic
    def create(self, validated):
        business = Business.objects.create(
            name=validated["business_name"],
            email=validated["email"],
            phone=validated.get("phone", ""),
            city=validated.get("city", ""),
            business_type=validated["business_type"],
        )
        owner = User.objects.create_user(
            email=validated["email"],
            password=validated["password"],
            first_name=validated["first_name"],
            last_name=validated.get("last_name", ""),
            phone=validated.get("phone", ""),
            business=business,
            is_owner=True,
        )
        seed_business_defaults(business, owner)
        return owner


class LoginSerializer(TokenObtainPairSerializer):
    require_owner = False
    require_platform_admin = False
    require_cashier = False

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["is_owner"] = user.is_owner
        token["is_platform_admin"] = bool(getattr(user, "is_platform_admin", False))
        if user.business_id:
            token["business_id"] = str(user.business_id)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        is_owner = bool(getattr(self.user, "is_owner", False))
        is_platform = bool(getattr(self.user, "is_platform_admin", False))
        if self.require_platform_admin:
            if not is_platform:
                raise serializers.ValidationError(
                    "This portal is for platform administrators only."
                )
        elif is_platform:
            raise serializers.ValidationError(
                "Use the platform admin portal to sign in."
            )
        if self.require_cashier:
            if is_owner or not is_cashier_user(self.user):
                raise serializers.ValidationError(
                    "This portal is for cashiers only. Use the business owner sign-in."
                )
        elif is_cashier_user(self.user):
            raise serializers.ValidationError(
                "Use the cashier portal to sign in."
            )
        if self.require_owner and not is_owner:
            raise serializers.ValidationError(
                "This portal is for business owners only. Sign in from the staff page."
            )
        if (
            not is_platform
            and self.user.business_id
            and not self.user.business.is_active
        ):
            raise serializers.ValidationError(
                "This business is disabled. Contact the platform administrator."
            )
        self.user.last_login = timezone.now()
        self.user.save(update_fields=["last_login"])
        data["user"] = MeSerializer(self.user).data
        return data


class OwnerLoginSerializer(LoginSerializer):
    require_owner = True


class PlatformLoginSerializer(LoginSerializer):
    require_platform_admin = True


class CashierLoginSerializer(LoginSerializer):
    require_cashier = True


class CreateCashierSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, write_only=True)
    default_branch = serializers.UUIDField(required=False, allow_null=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate_default_branch(self, value):
        if not value:
            return value
        from apps.businesses.models import Branch

        business = self.context["request"].user.business
        if not Branch.objects.filter(business=business, id=value).exists():
            raise serializers.ValidationError("Branch does not belong to this business.")
        return value

    def create(self, validated):
        from apps.businesses.models import Branch

        request = self.context["request"]
        business = request.user.business
        role = cashier_role_for(business)
        branch_id = validated.get("default_branch")
        branch = None
        if branch_id:
            branch = Branch.objects.filter(business=business, id=branch_id).first()
        if not branch:
            branch = Branch.objects.filter(business=business, is_head_office=True).first() or Branch.objects.filter(
                business=business
            ).first()
        user = User.objects.create_user(
            email=validated["email"],
            password=validated["password"],
            first_name=validated["first_name"],
            last_name=validated.get("last_name", ""),
            phone=validated.get("phone", ""),
            business=business,
            role=role,
            default_branch=branch,
            is_owner=False,
        )
        if branch:
            user.branches.set([branch])
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
