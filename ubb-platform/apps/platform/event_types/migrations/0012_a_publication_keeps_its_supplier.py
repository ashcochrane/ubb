"""A publication keeps its supplier (#572, #605; the consultant's review of #618).

The copy a publication keeps (`published_declaration`, #573) held everything
publication pinned except the supplier, which recording read live off the Event
Type's Provider. #572 made that supplier decide whose call a recording is — a
caller naming another is refused, and supplier cost resolves under it — so a
live read let a Provider rename, or an Event Type re-pointed at another Provider,
change what production admits and how it costs with nobody publishing anything:
the drift #605 removed for every other fact recording reads. From here the
supplier is pinned by its identity, a rename revises the declarations naming
it, and the copy keeps the Provider's KEY under `provider_key`.

**A copy kept before this migration says nothing about its supplier.** This
writes into each the key of the Provider its Event Type names as the migration
runs — the supplier recording was reading, live, the instant before. It is not a
guess at the past: no earlier publication stated a supplier, recording costed
every call under the live one, and this freezes exactly that, so nothing an
integration sends is answered differently on the far side of the migration. An
Event Type naming no Provider keeps `""`. A copy that already carries one is
left as it is.

The reverse takes the key out of every copy again: the code before this reads
the supplier live and has no use for it.
"""
from django.db import migrations

PROVIDER_KEY = "provider_key"


def keep_the_supplier(apps, schema_editor):
    EventType = apps.get_model("event_types", "EventType")
    for event_type in (EventType.objects
                       .filter(published_declaration__isnull=False)
                       .select_related("provider")):
        kept = dict(event_type.published_declaration)
        if PROVIDER_KEY in kept:
            continue
        kept[PROVIDER_KEY] = (event_type.provider.key
                              if event_type.provider_id is not None else "")
        EventType.objects.filter(pk=event_type.pk).update(
            published_declaration=kept)


def forget_the_supplier(apps, schema_editor):
    EventType = apps.get_model("event_types", "EventType")
    for event_type in (EventType.objects
                       .filter(published_declaration__isnull=False)):
        kept = dict(event_type.published_declaration)
        if kept.pop(PROVIDER_KEY, None) is None:
            continue
        EventType.objects.filter(pk=event_type.pk).update(
            published_declaration=kept)


class Migration(migrations.Migration):

    dependencies = [
        ("event_types",
         "0011_a_declaration_is_not_deleted_from_under_its_held_names"),
    ]

    operations = [
        migrations.RunPython(keep_the_supplier, forget_the_supplier),
    ]
