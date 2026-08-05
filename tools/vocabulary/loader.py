"""YAML loading that refuses a duplicate key.

PyYAML's ``safe_load`` accepts a mapping with the same key twice and keeps the
last one. For a registry whose entire purpose is that a term is defined exactly
once, that is precisely the wrong default: the same concept written twice in one
file would load as one concept and pass every later check.

So the registry is never loaded with ``safe_load``. It is loaded with
:func:`load_yaml`, which turns a repeated key into a named failure.
"""

import yaml


class DuplicateKey(Exception):
    """A mapping key that appears more than once in one YAML document."""

    def __init__(self, key, line):
        self.key = key
        self.line = line
        super().__init__(f"duplicate key {key!r} at line {line}")


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader, minus the silent last-one-wins duplicate-key behaviour."""


def _construct_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DuplicateKey(key, key_node.start_mark.line + 1)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_yaml(text):
    """Parse one YAML document, raising :class:`DuplicateKey` on a repeat.

    Raises ``yaml.YAMLError`` for anything else malformed; the caller turns both
    into registry errors with a location attached.
    """
    return yaml.load(text, Loader=_StrictLoader)
