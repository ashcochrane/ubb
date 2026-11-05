"""Shared helpers for tests that drive the Tenant admin."""
from django import forms


def the_forms_own_post(form, **changes):
    """The admin form's own current values, as a browser would post them,
    with `changes` applied — so the post is the form's, not the test's.

    The tenant's two JSON settings are required by the form and an empty
    object reads as empty, so an operator fills each in; this post does too,
    so the only thing that can refuse it is the rule under test.
    """
    changes = {"branding_config": {"filled_in": "by the operator"},
               "metadata": {"filled_in": "by the operator"}, **changes}
    data = {}
    for name, field in form.fields.items():
        value = changes.get(name, form[name].value())
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = "on"
            continue
        if value is None:
            data[name] = ""
        elif isinstance(value, str):
            data[name] = value
        else:
            data[name] = field.prepare_value(value)
    return data
