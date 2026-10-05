import json

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "universal-pos"})


class AppUpdateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        payload = {
            "version": "1.0.0",
            "message": "A new version of Universal POS is available. Please update.",
            "downloadUrl": "",
        }
        path = settings.BASE_DIR / "release.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    payload.update({key: data.get(key, payload[key]) for key in payload})
            except (OSError, json.JSONDecodeError, TypeError):
                pass
        return Response(payload)
