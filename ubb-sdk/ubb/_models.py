"""Turn a wire response into a generated DTO — the shell's return-type contract.

The wrap (issue #84) abolishes hand-typed DTOs: product-client methods parse
their response through the generated ``ubb._core`` models instead. The generator
represents an absent optional field with its ``UNSET`` sentinel.

⚠ **THREE DIFFERENT FACTS, NEVER CONFLATED (#596; W5 ruling 13).** A field the
response left out, a field the response stated as ``null`` and a field holding a
falsy legal value (``0``, ``False``, ``""``, ``[]``) are three things, so
``from_wire`` normalizes by the field's DECLARED type and never by its value:

- an omitted field whose type admits ``None`` reads ``None`` — absence and null
  say the same thing about a nullable fact, so ``result.stop_reason is None``
  keeps working;
- an omitted field whose type does NOT admit ``None`` stays ``UNSET`` — test it
  with ``is UNSET`` (``ubb.UNSET``) or ``is_unset``, never with ``not x``, which
  would also be true of a ``0`` or an empty list the response did state;
- a value the response stated is never touched, falsy or not.

The rule is applied at every depth a generated model reaches — nested models,
lists of them, and their additional properties — so ``to_dict()`` works on every
model ``from_wire`` returns: the generated serialiser skips ``UNSET`` and writes
``None`` only where the type admits it. Before W5 the normalization was depth-1
and blind to the type, and ``to_dict()`` raised on any response that left out an
optional object field (``AttributeError: 'NoneType' object has no attribute
'to_dict'``).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import TypeVar

import attrs
from attrs import fields as _attrs_fields

from ubb._core.types import Unset

T = TypeVar("T")


def is_unset(value) -> bool:
    """Whether ``value`` is the core's ``UNSET`` — a field the response left
    out — as opposed to ``None`` (stated null) or a falsy value it stated."""
    return isinstance(value, Unset)


def _top_level_members(annotation: str) -> list[str]:
    """The members of a union annotation, split at bracket depth zero —
    ``"list[int | None] | Unset"`` is two members, not three."""
    members, depth, current = [], 0, ""
    for char in annotation:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "|" and depth == 0:
            members.append(current.strip())
            current = ""
        else:
            current += char
    members.append(current.strip())
    return members


@lru_cache(maxsize=None)
def _nullable_fields(model_cls) -> frozenset:
    """The fields of a generated model whose declared type admits ``None``.

    Read off the generated annotation (the core is ``from __future__ import
    annotations``, so each is a string such as ``"int | None | Unset"``).
    """
    nullable = set()
    for f in _attrs_fields(model_cls):
        annotation = f.type if isinstance(f.type, str) else repr(f.type)
        if "None" in _top_level_members(annotation):
            nullable.add(f.name)
    return frozenset(nullable)


def _normalize(value):
    """Apply the omitted-field rule to a model, a list, or anything else."""
    if attrs.has(type(value)):
        return _normalize_unset(value)
    if isinstance(value, list):
        for item in value:
            _normalize(item)
    return value


def _normalize_unset(obj: T) -> T:
    nullable = _nullable_fields(type(obj))
    for f in _attrs_fields(type(obj)):
        value = getattr(obj, f.name)
        if isinstance(value, Unset):
            if f.name in nullable:
                setattr(obj, f.name, None)
        elif f.name == "additional_properties" and isinstance(value, dict):
            for item in value.values():
                _normalize(item)
        else:
            _normalize(value)
    return obj


def token(value):
    """A closed value as its registry token, for a shell surface typed ``str``.

    The core holds a field whose concept is closed as a ``str``-``Enum``
    member, which compares equal to its token but REPRS as the class — so a
    hand-written surface that promises ``str`` (and code that logs it with
    ``%r``) answers the token itself. ``None`` stays ``None``.
    """
    return value.value if isinstance(value, Enum) else value


def from_wire(model_cls: type[T], data: dict) -> T:
    """Parse ``data`` into a generated model, UNSET-normalized (see module doc)."""
    return _normalize_unset(model_cls.from_dict(data))


def list_from_wire(model_cls: type[T], rows: list[dict]) -> list[T]:
    """``from_wire`` over a list of rows (e.g. a page of items)."""
    return [from_wire(model_cls, row) for row in rows]


def page_from_wire(model_cls: type[T], body: dict):
    """The cursor envelope every list answers — ``data`` / ``next_cursor`` /
    ``has_more`` (MIGRATION.md §2) — with its rows parsed through
    ``model_cls``. One reader for the one envelope, so a list method names its
    row model and nothing else."""
    from ubb.types import PaginatedResponse  # the shell type; imported here
    return PaginatedResponse(data=list_from_wire(model_cls, body["data"]),
                             next_cursor=body.get("next_cursor"),
                             has_more=body["has_more"])
