from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.businesses.models import Business, BusinessType
from apps.hostel.models import HostelBed, HostelCustomer, HostelPayment, HostelReservation

User = get_user_model()


class HostelWorkflowTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(name="ABC Hostel", business_type=BusinessType.HOSTEL, city="Lahore")
        self.owner = User.objects.create_user(email="owner@hostel.test", password="owner-pass-1", business=self.business, is_owner=True, first_name="Owner")
        self.other = Business.objects.create(name="Grocery", business_type=BusinessType.GENERAL)
        self.retail = User.objects.create_user(email="shop@hostel.test", password="shop-pass-1", business=self.other, is_owner=True)
        self.client.force_authenticate(self.owner)

    def test_retail_business_cannot_open_hostel(self):
        self.client.force_authenticate(self.retail)
        response = self.client.get("/api/hostel/me/")
        self.assertEqual(response.status_code, 403)

    def test_booking_payment_and_branch_isolation(self):
        first = self.client.post("/api/hostel/branches/", {"name": "Lahore", "code": "LHR", "address": "Mall Road", "phone": "03001234567", "floors": 2, "monthly_rent": "15000", "security_deposit": "5000"}, format="json")
        second = self.client.post("/api/hostel/branches/", {"name": "Karachi", "code": "KHI", "address": "Clifton", "floors": 1}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        lahore = first.data["id"]
        karachi = second.data["id"]

        room = self.client.post("/api/hostel/rooms/", {"branch": lahore, "number": "204", "floor": 2, "room_type": "double", "monthly_rent": "15000", "security_deposit": "5000", "wifi": True}, format="json")
        self.assertEqual(room.status_code, 201, room.data)
        self.assertEqual(len(room.data["beds"]), 2)
        bed = room.data["beds"][0]["id"]
        other_bed = room.data["beds"][1]["id"]

        customer = self.client.post("/api/hostel/customers/", {
            "full_name": "Muhammad Ali", "mobile": "03001111111", "whatsapp": "03001111111",
            "cnic": "35202-1234567-1", "branch": lahore, "monthly_rent": "15000",
            "security_deposit": "5000", "registration_fee": "1000",
        }, format="json")
        self.assertEqual(customer.status_code, 201, customer.data)
        customer_id = customer.data["id"]

        clash_a = self.client.post("/api/hostel/reservations/", {
            "customer": customer_id, "bed": bed, "check_in_date": "2026-03-01", "expected_checkout": "2026-06-01",
            "monthly_rent": "15000", "security_deposit": "5000", "advance_payment": "0",
        }, format="json")
        self.assertEqual(clash_a.status_code, 201, clash_a.data)
        clash_b = self.client.post("/api/hostel/reservations/", {
            "customer": customer_id, "bed": bed, "check_in_date": "2026-04-01", "expected_checkout": "2026-07-01",
            "monthly_rent": "15000",
        }, format="json")
        self.assertEqual(clash_b.status_code, 400)

        other_ok = self.client.post("/api/hostel/reservations/", {
            "customer": customer_id, "bed": other_bed, "check_in_date": "2026-08-01", "expected_checkout": "2026-09-01",
            "monthly_rent": "15000", "status": "pending",
        }, format="json")
        self.assertEqual(other_ok.status_code, 201, other_ok.data)

        checked = self.client.post(f"/api/hostel/reservations/{clash_a.data['id']}/check-in/", {}, format="json")
        self.assertEqual(checked.status_code, 200, checked.data)
        self.assertEqual(HostelBed.objects.get(pk=bed).status, HostelBed.Status.OCCUPIED)

        generated = self.client.post("/api/hostel/billing/generate/", {"year": 2026, "month": 3, "branch": lahore}, format="json")
        self.assertEqual(generated.status_code, 200)
        partial = self.client.post("/api/hostel/payments/", {
            "customer": customer_id, "amount": "5000", "payment_type": "rent", "method": "cash",
            "payment_date": "2026-03-05", "period_year": 2026, "period_month": 3,
        }, format="json")
        self.assertEqual(partial.status_code, 201, partial.data)
        bill = self.client.get("/api/hostel/monthly/?customer=" + customer_id + "&year=2026&month=3")
        self.assertEqual(bill.data["results"][0]["status"], "partial")
        rest = self.client.post("/api/hostel/payments/", {
            "customer": customer_id, "amount": "10000", "payment_type": "rent", "method": "jazzcash",
            "payment_date": "2026-03-06", "period_year": 2026, "period_month": 3, "transaction_id": "JC1",
        }, format="json")
        self.assertEqual(rest.status_code, 201, rest.data)
        bill = self.client.get("/api/hostel/monthly/?customer=" + customer_id + "&year=2026&month=3")
        self.assertEqual(bill.data["results"][0]["status"], "paid")

        power = self.client.post("/api/hostel/payments/", {
            "customer": customer_id, "amount": "2000", "payment_type": "electricity", "method": "cash",
            "payment_date": "2026-03-07", "period_year": 2026, "period_month": 3,
        }, format="json")
        self.assertEqual(power.status_code, 201)
        profile = self.client.get(f"/api/hostel/customers/{customer_id}/")
        self.assertEqual(Decimal(profile.data["finance"]["remaining"]), Decimal("6000.00"))
        self.assertEqual(HostelPayment.objects.filter(customer_id=customer_id, is_void=False).count(), 3)

        voided = self.client.delete(f"/api/hostel/payments/{power.data['id']}/")
        self.assertEqual(voided.status_code, 204)
        self.assertTrue(HostelPayment.objects.get(pk=power.data["id"]).is_void)
        profile = self.client.get(f"/api/hostel/customers/{customer_id}/")
        self.assertEqual(Decimal(profile.data["finance"]["total_paid"]), Decimal("15000.00"))

        staff = self.client.post("/api/hostel/employees/", {
            "full_name": "Sara Khan", "email": "sara@hostel.test", "password": "staff-pass-1",
            "phone": "03002222222", "branch": lahore, "role": "employee", "designation": "Warden",
            "joining_date": "2026-01-01", "salary": "40000",
        }, format="json")
        self.assertEqual(staff.status_code, 201, staff.data)
        self.client.force_authenticate(User.objects.get(email="sara@hostel.test"))
        denied = self.client.get(f"/api/hostel/customers/?branch={karachi}")
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.data["count"], 0)
        own = self.client.get("/api/hostel/customers/")
        self.assertEqual(own.data["count"], 1)
        report = self.client.get("/api/hostel/reports/?type=collections")
        self.assertEqual(report.status_code, 403)
        cannot_void = self.client.delete(f"/api/hostel/payments/{partial.data['id']}/")
        self.assertEqual(cannot_void.status_code, 403)
        removed = self.client.delete(f"/api/hostel/branches/{lahore}/")
        self.assertIn(removed.status_code, (403, 404))

        self.client.force_authenticate(self.owner)
        blocked = self.client.delete(f"/api/hostel/branches/{lahore}/")
        self.assertEqual(blocked.status_code, 400)
        closed = self.client.post(f"/api/hostel/reservations/{clash_a.data['id']}/check-out/", {}, format="json")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(HostelBed.objects.get(pk=bed).status, HostelBed.Status.AVAILABLE)
        self.assertEqual(HostelReservation.objects.get(pk=clash_a.data["id"]).status, HostelReservation.Status.COMPLETED)
        self.assertEqual(HostelCustomer.objects.get(pk=customer_id).bed_id, None)

    def test_staff_can_sign_in_from_owner_portal(self):
        branch = self.client.post("/api/hostel/branches/", {"name": "Lahore", "code": "LHR2", "floors": 1}, format="json")
        self.client.post("/api/hostel/employees/", {
            "full_name": "Bilal", "email": "bilal@hostel.test", "password": "staff-pass-1",
            "branch": branch.data["id"], "role": "manager", "can_view_reports": True, "can_approve_expenses": True,
        }, format="json")
        self.client.logout()
        response = self.client.post("/api/auth/owner/login/", {"email": "bilal@hostel.test", "password": "staff-pass-1"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["is_owner"], False)
