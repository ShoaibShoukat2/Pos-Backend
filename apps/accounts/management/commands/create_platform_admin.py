from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update the software-owner account for the platform dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--first-name", default="Platform")
        parser.add_argument("--last-name", default="Admin")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        password = options["password"]
        if not email or not password:
            raise CommandError("Email and password are required.")

        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created:
            user = User(email=email)
        user.first_name = options["first_name"]
        user.last_name = options["last_name"]
        user.business = None
        user.role = None
        user.is_owner = False
        user.is_platform_admin = True
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} platform admin {user.email}"))
