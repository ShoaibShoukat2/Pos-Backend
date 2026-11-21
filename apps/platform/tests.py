from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.businesses.models import Business, BusinessType
from apps.businesses.subscription import EXPIRED_MESSAGE

User = get_user_model()


class BusinessSubscriptionTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Clock Shop", business_type=BusinessType.GENERAL, city="Lahore")
        self.owner = User.objects.create_user(
            email="owner-sub@shop.test",
            password="owner-pass-1",
            business=self.business,
            is_owner=True,
            first_name="Owner",
        )
        self.admin = User.objects.create_user(
            email="platform-sub@shop.test",
            password="admin-pass-1",
            is_platform_admin=True,
            first_name="Admin",
        )

    def login(self):
        self.client.force_authenticate(user=None)
        return self.client.post(
            "/api/auth/owner/login/",
            {"email": "owner-sub@shop.test", "password": "owner-pass-1"},
            format="json",
        )

    def test_admin_can_stop_shift_renew_and_delete_a_business(self):
        open_login = self.login()
        self.assertEqual(open_login.status_code, 200, open_login.data)

        self.client.force_authenticate(self.admin)
        stopped = self.client.post(f"/api/platform/businesses/{self.business.id}/subscription/", {"action": "stop"}, format="json")
        self.assertEqual(stopped.status_code, 200, stopped.data)
        self.assertEqual(stopped.data["subscription_status"], "expired")

        denied = self.login()
        self.assertEqual(denied.status_code, 400, denied.data)
        self.assertIn(EXPIRED_MESSAGE, str(denied.data))

        self.client.force_authenticate(self.admin)
        renewed = self.client.post(f"/api/platform/businesses/{self.business.id}/subscription/", {"action": "activate"}, format="json")
        self.assertEqual(renewed.status_code, 200, renewed.data)
        self.assertEqual(renewed.data["subscription_ends_on"], (timezone.localdate() + timedelta(days=30)).isoformat())
        self.assertEqual(self.login().status_code, 200)

        self.client.force_authenticate(self.admin)
        shifted = self.client.post(
            f"/api/platform/businesses/{self.business.id}/subscription/",
            {"action": "shift", "days": -40},
            format="json",
        )
        self.assertEqual(shifted.status_code, 200, shifted.data)
        self.assertEqual(shifted.data["subscription_status"], "expired")
        self.assertEqual(self.login().status_code, 400)

        self.client.force_authenticate(self.admin)
        forward = self.client.post(
            f"/api/platform/businesses/{self.business.id}/subscription/",
            {"action": "shift", "days": 50},
            format="json",
        )
        self.assertEqual(forward.status_code, 200, forward.data)
        self.assertEqual(forward.data["subscription_status"], "active")
        self.assertEqual(self.login().status_code, 200)

        self.client.force_authenticate(self.admin)
        removed = self.client.delete(f"/api/platform/businesses/{self.business.id}/")
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(Business.objects.filter(pk=self.business.id).exists())
        self.assertFalse(User.objects.filter(email="owner-sub@shop.test").exists())
