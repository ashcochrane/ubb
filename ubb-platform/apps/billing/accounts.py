def resolve_billing_owner(customer):
    return customer.resolve_billing_owner()


def resolve_billing_owner_id(customer):
    return customer.resolve_billing_owner().id


def billing_owner_ids(customers):
    """The canonical billing owner of each customer, as a set of ids — a
    pooled seat's business, everyone else themselves (an allocated seat
    included).

    THE ONE LOOP both owner-keyed passes run over the customers that recorded
    usage in a period: the hourly owner reconcile (`gating/tasks.py`) and the
    monthly postpaid close (`invoicing/tasks.py`, R10 Stage C3, F-7, which keyed
    any seat with a parent on that parent until then). Pass a queryset with the
    parent pre-loaded (`select_related("parent")`) or each seat reads it apart."""
    return {customer.resolve_billing_owner().id for customer in customers}
