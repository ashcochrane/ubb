import uuid

from django.contrib.postgres.indexes import BTreeIndex
from django.db import models


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PostgresNamedIndex(BTreeIndex):
    """A plain btree index whose name may use PostgreSQL's whole identifier length.

    Django caps a `models.Index` name at 30 characters for cross-database (Oracle)
    compatibility (check `models.E034`), and waives the cap for its own
    PostgreSQL-specific indexes only by the length of their suffix. UBB runs on
    PostgreSQL alone — its database rules are plpgsql triggers — and PostgreSQL
    identifiers hold 63 bytes, so an index whose canonical name is longer than 30
    is declared through this class rather than abbreviated. It builds the same
    btree index `models.Index` does.
    """

    max_name_length = 63
