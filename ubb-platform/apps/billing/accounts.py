def resolve_billing_owner(customer):
    """The Customer whose wallet/card/auto-top-up funds this customer:
    the business for a POOLED seat, otherwise the customer itself
    (individual, allocated seat, or business)."""
    if customer.account_type == "seat" and customer.parent_id:
        parent = customer.parent
        if parent.billing_topology == "pooled":
            return parent
    return customer


def resolve_billing_owner_id(customer):
    return resolve_billing_owner(customer).id
