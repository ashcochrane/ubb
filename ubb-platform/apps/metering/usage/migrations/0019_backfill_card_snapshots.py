"""Populate card_slug/card_name snapshots for events that already have a card FK."""

from django.db import migrations


def backfill_forward(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    Card = apps.get_model("pricing", "Card")

    # Get all events with a card FK and empty card_slug
    events_to_update = list(UsageEvent.objects.filter(card__isnull=False, card_slug="").values("id", "card_id"))

    # Bulk fetch cards
    card_ids = {ev["card_id"] for ev in events_to_update}
    cards = {card.id: card for card in Card.objects.filter(id__in=card_ids)}

    # Prepare updates
    updates = []
    for event_data in events_to_update:
        card = cards.get(event_data["card_id"])
        if card:
            updates.append(
                UsageEvent(
                    id=event_data["id"],
                    card_slug=card.slug or "",
                    card_name=card.name or "",
                )
            )

    # Bulk update using F expressions to avoid full model load
    if updates:
        UsageEvent.objects.bulk_update(updates, ["card_slug", "card_name"], batch_size=1000)


def backfill_reverse(apps, schema_editor):
    UsageEvent = apps.get_model("usage", "UsageEvent")
    UsageEvent.objects.update(card_slug="", card_name="")


class Migration(migrations.Migration):
    dependencies = [
        ("usage", "0018_usageevent_card_snapshot_fields"),
    ]
    operations = [migrations.RunPython(backfill_forward, backfill_reverse)]
