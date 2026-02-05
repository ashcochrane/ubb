# Re-export Invoice from its current Django app location.
# The Invoice model is conceptually a billing model but lives in
# apps.metering.usage.models for Django migration history reasons
# (it was created there before the product separation).
# This re-export allows billing code to import from within its own domain.
from apps.metering.usage.models import Invoice, INVOICE_STATUS_CHOICES  # noqa: F401
