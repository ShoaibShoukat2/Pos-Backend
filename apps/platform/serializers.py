from rest_framework import serializers

from apps.accounts.models import User
from apps.businesses.models import Business


class PlatformBusinessSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    branch_count = serializers.IntegerField(read_only=True)
    product_count = serializers.IntegerField(read_only=True)
    customer_count = serializers.IntegerField(read_only=True)
    sale_count = serializers.IntegerField(read_only=True)
    owner_email = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = Business
        fields = (
            "id",
            "name",
            "legal_name",
            "email",
            "phone",
            "city",
            "country",
            "business_type",
            "is_active",
            "user_count",
            "branch_count",
            "product_count",
            "customer_count",
            "sale_count",
            "owner_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "name",
            "legal_name",
            "email",
            "phone",
            "city",
            "country",
            "business_type",
            "user_count",
            "branch_count",
            "product_count",
            "customer_count",
            "sale_count",
            "owner_email",
            "created_at",
            "updated_at",
        )


class PlatformUserSerializer(serializers.ModelSerializer):
    business_name = serializers.SerializerMethodField()
    role_name = serializers.SerializerMethodField()

    def get_business_name(self, obj):
        return obj.business.name if obj.business_id else None

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else None

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
            "role_name",
            "business",
            "business_name",
            "date_joined",
            "last_login",
        )
        read_only_fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "is_owner",
            "role_name",
            "business",
            "business_name",
            "date_joined",
            "last_login",
        )
