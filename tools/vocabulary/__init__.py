"""The domain-vocabulary registry: its semantics, in one implementation.

`domain-vocabulary/` at the git root is the checked-in statement of the agreed
model (ADR-0008 §2). This package reads it. It has no Django, no database and no
settings, because the platform, the SDK and the console tooling all consume the
same registry and must not each grow their own parser.

    from tools.vocabulary import load_registry
    registry = load_registry("domain-vocabulary")

`python -m tools.vocabulary` runs the same check from a shell.
"""

from .compiler import (
    Concept,
    Consumer,
    KindRule,
    Registry,
    Schema,
    Surface,
    load_registry,
)
from .errors import RegistryError, RegistryInvalid

__all__ = [
    "Concept",
    "Consumer",
    "KindRule",
    "Registry",
    "RegistryError",
    "RegistryInvalid",
    "Schema",
    "Surface",
    "load_registry",
]
