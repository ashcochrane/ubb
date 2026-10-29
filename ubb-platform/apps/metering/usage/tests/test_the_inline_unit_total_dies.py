"""The posting's inline unit total is gone (#272).

Slice 2 had to settle whether the child record #270 created carries one column
or two. **One.** The nameless inline total did not follow the quantities across;
it died. Under the split it would have acquired a SHORTER LIFE than the billed
total beside it on the same response — the child is prunable and the money is
not — while the read contract's `or 0` coalescing went on rendering its absence
as a currency zero on the end customer's own view. Retiring it deleted that
failure mode instead of instrumenting it.

TWO DIFFERENT CLAIMS LIVE HERE, and only the first is about this database.

1. **The column is gone**, from the model and from the table — two separate
   claims, both asserted below.
2. **Every READER is gone** — the read contract, six public schemas, the
   customer-facing summary, the SDK and the console. That claim spans four
   surfaces, so it is not this module's; it belongs to
   `tests/contracts/test_the_inline_unit_total_is_gone.py`, which can see all of
   them at once. Both are needed: a column dropped while a reader survives is a
   500, and a reader deleted while the column survives is a retirement that did
   not happen.

Before the cutover (#190) this module also drove the DROP: `usage/0032`'s
`RemoveField`, backwards and forwards against the real table, holding that its
reverse restored the column's shape (nullable) and not its contents, and that
the migration removed exactly this one field. Those were facts about one
migration, and they retired with the chain.
"""

from django.db import connection
from django.test import TestCase

from apps.metering.usage.models import Posting

#: The column, by the name the database knew it by. A retired SENSE rather
#: than a retired alias (`retired.yaml`, `measurement_key`), so it is spelled.
COLUMN = "units"


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name: column for column in
                connection.introspection.get_table_description(
                    cursor, Posting._meta.db_table)}


class TheColumnIsGoneTest(TestCase):
    def test_the_model_declares_no_such_field(self):
        assert COLUMN not in {field.name for field in Posting._meta.get_fields()}

    def test_the_table_carries_no_such_column(self):
        """The model and the table are two separate claims.

        A field absent from the model while the schema still carries it leaves
        the column in the database, where the next `makemigrations` would offer
        to drop it and a raw query would still find it.
        """
        assert COLUMN not in _live_columns()
