from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from risks.models import Risk

class Command(BaseCommand):
    help = "Delete rejected risks older than 15 days"

    def handle(self, *args, **kwargs):
        cutoff = timezone.now() - timedelta(days=15)

        qs = Risk.objects.filter(
            approval_status="rejected",
            rejected_at__lte=cutoff
        )

        count = qs.count()
        qs.delete()

        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} rejected risks older than 15 days.")
        )
