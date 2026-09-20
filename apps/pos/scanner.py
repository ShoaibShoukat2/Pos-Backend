import secrets
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.branch import resolve_branch
from apps.core.permissions import HasAnyPermission
from apps.pos.models import ScannerEvent, ScannerSession


def _live_session(token: str) -> ScannerSession:
    session = ScannerSession.objects.filter(token=token, is_active=True).select_related("branch", "business").first()
    if not session:
        raise ValidationError({"detail": "Scanner link is not valid."})
    if session.expires_at < timezone.now():
        session.is_active = False
        session.save(update_fields=["is_active"])
        raise ValidationError({"detail": "Scanner link has expired. Generate a new QR."})
    return session


class ScannerOpenView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("pos.access", "sale.create")

    def post(self, request):
        branch = resolve_branch(request, required=False) or request.user.default_branch
        if not branch:
            raise ValidationError({"branch": "Shop is not set up."})
        session = ScannerSession.objects.create(
            business=request.user.business,
            branch=branch,
            token=secrets.token_urlsafe(18),
            created_by=request.user,
            expires_at=timezone.now() + timedelta(hours=8),
        )
        return Response(
            {
                "token": session.token,
                "branch": branch.name,
                "expires_at": session.expires_at.isoformat(),
                "connected": False,
            },
            status=201,
        )


class ScannerPullView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("pos.access", "sale.create")

    def get(self, request, token):
        session = _live_session(token)
        if session.business_id != request.user.business_id:
            raise ValidationError({"detail": "Scanner session belongs to another business."})
        events = list(session.events.filter(consumed=False)[:20])
        for event in events:
            event.consumed = True
            event.save(update_fields=["consumed"])
        return Response(
            {
                "connected": bool(session.connected_at),
                "branch": session.branch.name,
                "codes": [event.code for event in events],
            }
        )


class ScannerStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        session = _live_session(token)
        if not session.connected_at:
            session.connected_at = timezone.now()
            session.save(update_fields=["connected_at"])
        return Response(
            {
                "ok": True,
                "business": session.business.name,
                "branch": session.branch.name,
            }
        )


class ScannerPushView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, token):
        session = _live_session(token)
        code = str(request.data.get("code") or "").strip()
        if not code:
            raise ValidationError({"code": "Scan a barcode or QR code."})
        if not session.connected_at:
            session.connected_at = timezone.now()
            session.save(update_fields=["connected_at"])
        ScannerEvent.objects.create(session=session, code=code[:120])
        return Response({"ok": True, "code": code})
