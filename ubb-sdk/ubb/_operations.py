# @generated from openapi/v1.json and gates/migration-ledger.yaml — do not edit by hand.
# Regenerate with `python -m tools.sdk_operations --write`.
"""Every operation this SDK can reach, named by the contract that publishes it.

The single place in `ubb-sdk/ubb/` where a versioned path is spelled (#209,
#155 §8.3). A hand-written method references a constant here rather than
carrying a path string of its own, so renaming an operation in the contract
renames its constant and every stale reference stops resolving — which is
checked by `tools/sdk_operations`, in CI, before anything is called.

Two call shapes, decided by the path rather than by preference::

    self._request(*ops.API_V1_TENANT_ENDPOINTS_GET_TENANT_CONFIG)
    self._request(*ops.API_V1_PLAN_ENDPOINTS_UPDATE_PLAN(key), json=body)

A route with no parameters unpacks; a route with parameters is called with one
value per position, in the order the path spells them. Getting that wrong is a
`TypeError` from :class:`ubb._operation.Operation` and a red gate before that.

Constants prefixed `UNPUBLISHED_` name routes the contract does NOT publish.
They exist because three methods call them and the migration ledger excuses
those calls until slice 4 removes the methods. They are generated from the
ledger, so a debt cannot be quietly paid: delete the entry and the constant
goes with it.
"""

from ubb._operation import Operation

# --- published operations ----------------------------------------------------
#
# One per operation in openapi/v1.json, named for its `operationId`.
# Sorted by name, so a contract that gains an operation produces one insertion
# rather than a reshuffle nobody can review.

API_V1_AUDIT_ENDPOINTS_LIST_AUDIT_RECORDS = Operation(
    'api_v1_audit_endpoints_list_audit_records', 'get', '/api/v1/audit/records')
API_V1_BILLING_ENDPOINTS_CONFIGURE_AUTO_TOP_UP = Operation(
    'api_v1_billing_endpoints_configure_auto_top_up',
    'put',
    '/api/v1/billing/customers/{customer_id}/auto-top-up')
API_V1_BILLING_ENDPOINTS_CREATE_GRANT = Operation(
    'api_v1_billing_endpoints_create_grant',
    'post',
    '/api/v1/billing/customers/{customer_id}/grants')
API_V1_BILLING_ENDPOINTS_CREATE_TOP_UP = Operation(
    'api_v1_billing_endpoints_create_top_up',
    'post',
    '/api/v1/billing/customers/{customer_id}/top-up')
API_V1_BILLING_ENDPOINTS_CREDIT = Operation(
    'api_v1_billing_endpoints_credit', 'post', '/api/v1/billing/credit')
API_V1_BILLING_ENDPOINTS_DEBIT = Operation(
    'api_v1_billing_endpoints_debit', 'post', '/api/v1/billing/debit')
API_V1_BILLING_ENDPOINTS_GET_BALANCE = Operation(
    'api_v1_billing_endpoints_get_balance',
    'get',
    '/api/v1/billing/customers/{customer_id}/balance')
API_V1_BILLING_ENDPOINTS_GET_CUSTOMER_BILLING_PROFILE = Operation(
    'api_v1_billing_endpoints_get_customer_billing_profile',
    'get',
    '/api/v1/billing/customers/{customer_id}/billing-profile')
API_V1_BILLING_ENDPOINTS_GET_CUSTOMER_BUDGET = Operation(
    'api_v1_billing_endpoints_get_customer_budget',
    'get',
    '/api/v1/billing/customers/{customer_id}/budget')
API_V1_BILLING_ENDPOINTS_GET_CUSTOMER_BUDGET_STATUS = Operation(
    'api_v1_billing_endpoints_get_customer_budget_status',
    'get',
    '/api/v1/billing/customers/{customer_id}/budget/status')
API_V1_BILLING_ENDPOINTS_GET_POSTPAID_CONFIG = Operation(
    'api_v1_billing_endpoints_get_postpaid_config',
    'get',
    '/api/v1/billing/postpaid-config')
API_V1_BILLING_ENDPOINTS_GET_TENANT_BUDGET = Operation(
    'api_v1_billing_endpoints_get_tenant_budget', 'get', '/api/v1/billing/budget')
API_V1_BILLING_ENDPOINTS_GET_TRANSACTIONS = Operation(
    'api_v1_billing_endpoints_get_transactions',
    'get',
    '/api/v1/billing/customers/{customer_id}/transactions')
API_V1_BILLING_ENDPOINTS_LIST_CUSTOMER_USAGE_INVOICES = Operation(
    'api_v1_billing_endpoints_list_customer_usage_invoices',
    'get',
    '/api/v1/billing/customers/{customer_id}/usage-invoices')
API_V1_BILLING_ENDPOINTS_LIST_GRANTS = Operation(
    'api_v1_billing_endpoints_list_grants',
    'get',
    '/api/v1/billing/customers/{customer_id}/grants')
API_V1_BILLING_ENDPOINTS_LIST_TENANT_USAGE_INVOICES = Operation(
    'api_v1_billing_endpoints_list_tenant_usage_invoices',
    'get',
    '/api/v1/billing/tenant/usage-invoices')
API_V1_BILLING_ENDPOINTS_PRE_CHECK = Operation(
    'api_v1_billing_endpoints_pre_check', 'post', '/api/v1/billing/pre-check')
API_V1_BILLING_ENDPOINTS_PUT_CUSTOMER_BILLING_PROFILE = Operation(
    'api_v1_billing_endpoints_put_customer_billing_profile',
    'put',
    '/api/v1/billing/customers/{customer_id}/billing-profile')
API_V1_BILLING_ENDPOINTS_PUT_CUSTOMER_BUDGET = Operation(
    'api_v1_billing_endpoints_put_customer_budget',
    'put',
    '/api/v1/billing/customers/{customer_id}/budget')
API_V1_BILLING_ENDPOINTS_PUT_POSTPAID_CONFIG = Operation(
    'api_v1_billing_endpoints_put_postpaid_config',
    'put',
    '/api/v1/billing/postpaid-config')
API_V1_BILLING_ENDPOINTS_PUT_TENANT_BUDGET = Operation(
    'api_v1_billing_endpoints_put_tenant_budget', 'put', '/api/v1/billing/budget')
API_V1_BILLING_ENDPOINTS_REFUND_USAGE = Operation(
    'api_v1_billing_endpoints_refund_usage',
    'post',
    '/api/v1/billing/customers/{customer_id}/refund')
API_V1_BILLING_ENDPOINTS_REVENUE_ANALYTICS = Operation(
    'api_v1_billing_endpoints_revenue_analytics',
    'get',
    '/api/v1/billing/analytics/revenue')
API_V1_BILLING_ENDPOINTS_VOID_GRANT = Operation(
    'api_v1_billing_endpoints_void_grant',
    'post',
    '/api/v1/billing/customers/{customer_id}/grants/{grant_id}/void')
API_V1_BILLING_ENDPOINTS_WITHDRAW = Operation(
    'api_v1_billing_endpoints_withdraw',
    'post',
    '/api/v1/billing/customers/{customer_id}/withdraw')
API_V1_CONNECT_ENDPOINTS_CONNECT_START = Operation(
    'api_v1_connect_endpoints_connect_start', 'post', '/api/v1/connect/start')
API_V1_CONNECT_ENDPOINTS_CONNECT_STATUS = Operation(
    'api_v1_connect_endpoints_connect_status', 'get', '/api/v1/connect/status')
API_V1_ENDPOINTS_HEALTH = Operation('api_v1_endpoints_health', 'get', '/api/v1/health')
API_V1_ENDPOINTS_PAST_LIMIT_REPORT = Operation(
    'api_v1_endpoints_past_limit_report',
    'get',
    '/api/v1/customers/{customer_id}/past-limit-report')
API_V1_ENDPOINTS_READY = Operation('api_v1_endpoints_ready', 'get', '/api/v1/ready')
API_V1_EVENT_TYPE_ENDPOINTS_DECLARE_EVENT_CATEGORY = Operation(
    'api_v1_event_type_endpoints_declare_event_category',
    'post',
    '/api/v1/event-categories')
API_V1_EVENT_TYPE_ENDPOINTS_DECLARE_EVENT_TYPE = Operation(
    'api_v1_event_type_endpoints_declare_event_type', 'post', '/api/v1/event-types')
API_V1_EVENT_TYPE_ENDPOINTS_DECLARE_MEASUREMENT = Operation(
    'api_v1_event_type_endpoints_declare_measurement',
    'put',
    '/api/v1/event-types/{key}/measurements/{code}')
API_V1_EVENT_TYPE_ENDPOINTS_DECLARE_PROVIDER = Operation(
    'api_v1_event_type_endpoints_declare_provider', 'post', '/api/v1/providers')
API_V1_EVENT_TYPE_ENDPOINTS_DECLARE_REPORTED_COST_MAPPING = Operation(
    'api_v1_event_type_endpoints_declare_reported_cost_mapping',
    'put',
    '/api/v1/event-types/{key}/reported-cost-mapping')
API_V1_EVENT_TYPE_ENDPOINTS_GET_EVENT_TYPE = Operation(
    'api_v1_event_type_endpoints_get_event_type', 'get', '/api/v1/event-types/{key}')
API_V1_EVENT_TYPE_ENDPOINTS_GET_REPORTED_COST_MAPPING = Operation(
    'api_v1_event_type_endpoints_get_reported_cost_mapping',
    'get',
    '/api/v1/event-types/{key}/reported-cost-mapping')
API_V1_EVENT_TYPE_ENDPOINTS_LIST_EVENT_CATEGORIES = Operation(
    'api_v1_event_type_endpoints_list_event_categories',
    'get',
    '/api/v1/event-categories')
API_V1_EVENT_TYPE_ENDPOINTS_LIST_EVENT_TYPES = Operation(
    'api_v1_event_type_endpoints_list_event_types', 'get', '/api/v1/event-types')
API_V1_EVENT_TYPE_ENDPOINTS_LIST_MEASUREMENTS = Operation(
    'api_v1_event_type_endpoints_list_measurements',
    'get',
    '/api/v1/event-types/{key}/measurements')
API_V1_EVENT_TYPE_ENDPOINTS_LIST_PROVIDERS = Operation(
    'api_v1_event_type_endpoints_list_providers', 'get', '/api/v1/providers')
API_V1_EVENT_TYPE_ENDPOINTS_PUBLISH_EVENT_TYPE = Operation(
    'api_v1_event_type_endpoints_publish_event_type',
    'post',
    '/api/v1/event-types/{key}/publish')
API_V1_EVENT_TYPE_ENDPOINTS_REVISE_EVENT_TYPE = Operation(
    'api_v1_event_type_endpoints_revise_event_type',
    'patch',
    '/api/v1/event-types/{key}')
API_V1_EVENT_TYPE_ENDPOINTS_REVISE_PROVIDER = Operation(
    'api_v1_event_type_endpoints_revise_provider', 'patch', '/api/v1/providers/{key}')
API_V1_EVENT_TYPE_ENDPOINTS_WITHDRAW_EVENT_CATEGORY = Operation(
    'api_v1_event_type_endpoints_withdraw_event_category',
    'delete',
    '/api/v1/event-categories/{key}')
API_V1_EVENT_TYPE_ENDPOINTS_WITHDRAW_MEASUREMENT = Operation(
    'api_v1_event_type_endpoints_withdraw_measurement',
    'delete',
    '/api/v1/event-types/{key}/measurements/{code}')
API_V1_EVENT_TYPE_ENDPOINTS_WITHDRAW_REPORTED_COST_MAPPING = Operation(
    'api_v1_event_type_endpoints_withdraw_reported_cost_mapping',
    'delete',
    '/api/v1/event-types/{key}/reported-cost-mapping')
API_V1_METERING_ENDPOINTS_ADD_RATE = Operation(
    'api_v1_metering_endpoints_add_rate',
    'post',
    '/api/v1/metering/pricing/rate-cards/{book_id}/rates')
API_V1_METERING_ENDPOINTS_ASSIGN_BOOK = Operation(
    'api_v1_metering_endpoints_assign_book',
    'post',
    '/api/v1/metering/pricing/customers/{customer_id}/rate-card')
API_V1_METERING_ENDPOINTS_CLOSE_TASK = Operation(
    'api_v1_metering_endpoints_close_task',
    'post',
    '/api/v1/metering/tasks/{task_id}/close')
API_V1_METERING_ENDPOINTS_CREATE_BOOK = Operation(
    'api_v1_metering_endpoints_create_book',
    'post',
    '/api/v1/metering/pricing/rate-cards')
API_V1_METERING_ENDPOINTS_DECLARE_DIMENSIONS = Operation(
    'api_v1_metering_endpoints_declare_dimensions',
    'put',
    '/api/v1/metering/dimensions')
API_V1_METERING_ENDPOINTS_DECLARE_TASK_TYPES = Operation(
    'api_v1_metering_endpoints_declare_task_types',
    'put',
    '/api/v1/metering/task-types')
API_V1_METERING_ENDPOINTS_DELETE_CUSTOMER_MARKUP = Operation(
    'api_v1_metering_endpoints_delete_customer_markup',
    'delete',
    '/api/v1/metering/pricing/customers/{customer_id}/markup')
API_V1_METERING_ENDPOINTS_DELETE_RATE = Operation(
    'api_v1_metering_endpoints_delete_rate',
    'delete',
    '/api/v1/metering/pricing/rate-cards/{book_id}/rates/{rate_id}')
API_V1_METERING_ENDPOINTS_GET_CUSTOMER_MARKUP = Operation(
    'api_v1_metering_endpoints_get_customer_markup',
    'get',
    '/api/v1/metering/pricing/customers/{customer_id}/markup')
API_V1_METERING_ENDPOINTS_GET_TASK = Operation(
    'api_v1_metering_endpoints_get_task', 'get', '/api/v1/metering/tasks/{task_id}')
API_V1_METERING_ENDPOINTS_GET_TENANT_MARKUP = Operation(
    'api_v1_metering_endpoints_get_tenant_markup',
    'get',
    '/api/v1/metering/pricing/markup')
API_V1_METERING_ENDPOINTS_GET_USAGE = Operation(
    'api_v1_metering_endpoints_get_usage',
    'get',
    '/api/v1/metering/customers/{customer_id}/usage')
API_V1_METERING_ENDPOINTS_GET_USAGE_EVENT = Operation(
    'api_v1_metering_endpoints_get_usage_event',
    'get',
    '/api/v1/metering/usage/{event_id}')
API_V1_METERING_ENDPOINTS_LIST_BOOKS = Operation(
    'api_v1_metering_endpoints_list_books',
    'get',
    '/api/v1/metering/pricing/rate-cards')
API_V1_METERING_ENDPOINTS_LIST_BOOK_RATES = Operation(
    'api_v1_metering_endpoints_list_book_rates',
    'get',
    '/api/v1/metering/pricing/rate-cards/{book_id}/rates')
API_V1_METERING_ENDPOINTS_LIST_DIMENSIONS = Operation(
    'api_v1_metering_endpoints_list_dimensions', 'get', '/api/v1/metering/dimensions')
API_V1_METERING_ENDPOINTS_LIST_DIMENSION_VALUES = Operation(
    'api_v1_metering_endpoints_list_dimension_values',
    'get',
    '/api/v1/metering/dimensions/{key}/values')
API_V1_METERING_ENDPOINTS_LIST_TASKS = Operation(
    'api_v1_metering_endpoints_list_tasks', 'get', '/api/v1/metering/tasks')
API_V1_METERING_ENDPOINTS_LIST_TASK_TYPES = Operation(
    'api_v1_metering_endpoints_list_task_types', 'get', '/api/v1/metering/task-types')
API_V1_METERING_ENDPOINTS_PUBLISH_BOOK = Operation(
    'api_v1_metering_endpoints_publish_book',
    'post',
    '/api/v1/metering/pricing/rate-cards/{book_id}/publish')
API_V1_METERING_ENDPOINTS_RECORD_USAGE = Operation(
    'api_v1_metering_endpoints_record_usage', 'post', '/api/v1/metering/usage')
API_V1_METERING_ENDPOINTS_RECORD_USAGE_BATCH = Operation(
    'api_v1_metering_endpoints_record_usage_batch',
    'post',
    '/api/v1/metering/usage/batch')
API_V1_METERING_ENDPOINTS_TASK_ANALYTICS = Operation(
    'api_v1_metering_endpoints_task_analytics',
    'get',
    '/api/v1/metering/analytics/tasks')
API_V1_METERING_ENDPOINTS_UPSERT_CUSTOMER_MARKUP = Operation(
    'api_v1_metering_endpoints_upsert_customer_markup',
    'put',
    '/api/v1/metering/pricing/customers/{customer_id}/markup')
API_V1_METERING_ENDPOINTS_UPSERT_TENANT_MARKUP = Operation(
    'api_v1_metering_endpoints_upsert_tenant_markup',
    'put',
    '/api/v1/metering/pricing/markup')
API_V1_METERING_ENDPOINTS_USAGE_ANALYTICS = Operation(
    'api_v1_metering_endpoints_usage_analytics',
    'get',
    '/api/v1/metering/analytics/usage')
API_V1_METERING_ENDPOINTS_USAGE_TIMESERIES = Operation(
    'api_v1_metering_endpoints_usage_timeseries',
    'get',
    '/api/v1/metering/analytics/usage/timeseries')
API_V1_ME_ENDPOINTS_CREATE_TOP_UP = Operation(
    'api_v1_me_endpoints_create_top_up', 'post', '/api/v1/me/top-up')
API_V1_ME_ENDPOINTS_GET_BALANCE = Operation(
    'api_v1_me_endpoints_get_balance', 'get', '/api/v1/me/balance')
API_V1_ME_ENDPOINTS_GET_INVOICES = Operation(
    'api_v1_me_endpoints_get_invoices', 'get', '/api/v1/me/invoices')
API_V1_ME_ENDPOINTS_GET_TRANSACTIONS = Operation(
    'api_v1_me_endpoints_get_transactions', 'get', '/api/v1/me/transactions')
API_V1_ME_ENDPOINTS_GET_USAGE_SUMMARY = Operation(
    'api_v1_me_endpoints_get_usage_summary', 'get', '/api/v1/me/usage-summary')
API_V1_ME_ENDPOINTS_LIST_GRANTS = Operation(
    'api_v1_me_endpoints_list_grants', 'get', '/api/v1/me/grants')
API_V1_ME_ENDPOINTS_LIST_SUBSCRIPTION_INVOICES = Operation(
    'api_v1_me_endpoints_list_subscription_invoices',
    'get',
    '/api/v1/me/subscription-invoices')
API_V1_ME_ENDPOINTS_LIST_USAGE_INVOICES = Operation(
    'api_v1_me_endpoints_list_usage_invoices', 'get', '/api/v1/me/usage-invoices')
API_V1_PLAN_ENDPOINTS_ARCHIVE_PLAN = Operation(
    'api_v1_plan_endpoints_archive_plan', 'delete', '/api/v1/plans/{key}')
API_V1_PLAN_ENDPOINTS_ASSIGN_PLAN = Operation(
    'api_v1_plan_endpoints_assign_plan', 'post', '/api/v1/customers/{external_id}/plan')
API_V1_PLAN_ENDPOINTS_CREATE_PLAN = Operation(
    'api_v1_plan_endpoints_create_plan', 'post', '/api/v1/plans')
API_V1_PLAN_ENDPOINTS_GET_PLAN = Operation(
    'api_v1_plan_endpoints_get_plan', 'get', '/api/v1/plans/{key}')
API_V1_PLAN_ENDPOINTS_LIST_PLANS = Operation(
    'api_v1_plan_endpoints_list_plans', 'get', '/api/v1/plans')
API_V1_PLAN_ENDPOINTS_UPDATE_PLAN = Operation(
    'api_v1_plan_endpoints_update_plan', 'patch', '/api/v1/plans/{key}')
API_V1_PLATFORM_ENDPOINTS_CREATE_CUSTOMER = Operation(
    'api_v1_platform_endpoints_create_customer', 'post', '/api/v1/platform/customers')
API_V1_PLATFORM_ENDPOINTS_GET_BUSINESS = Operation(
    'api_v1_platform_endpoints_get_business',
    'get',
    '/api/v1/platform/accounts/business/{external_id}')
API_V1_SANDBOX_ENDPOINTS_RESET_SANDBOX = Operation(
    'api_v1_sandbox_endpoints_reset_sandbox', 'post', '/api/v1/sandbox/reset')
API_V1_TENANT_ENDPOINTS_CREATE_API_KEY = Operation(
    'api_v1_tenant_endpoints_create_api_key', 'post', '/api/v1/tenant/api-keys')
API_V1_TENANT_ENDPOINTS_CREATE_INVITATION = Operation(
    'api_v1_tenant_endpoints_create_invitation', 'post', '/api/v1/tenant/invitations')
API_V1_TENANT_ENDPOINTS_CREATE_SANDBOX = Operation(
    'api_v1_tenant_endpoints_create_sandbox', 'post', '/api/v1/tenant/sandbox')
API_V1_TENANT_ENDPOINTS_GET_SANDBOX = Operation(
    'api_v1_tenant_endpoints_get_sandbox', 'get', '/api/v1/tenant/sandbox')
API_V1_TENANT_ENDPOINTS_GET_TENANT_CONFIG = Operation(
    'api_v1_tenant_endpoints_get_tenant_config', 'get', '/api/v1/tenant/config')
API_V1_TENANT_ENDPOINTS_LIST_API_KEYS = Operation(
    'api_v1_tenant_endpoints_list_api_keys', 'get', '/api/v1/tenant/api-keys')
API_V1_TENANT_ENDPOINTS_LIST_BILLING_PERIODS = Operation(
    'api_v1_tenant_endpoints_list_billing_periods',
    'get',
    '/api/v1/tenant/billing-periods')
API_V1_TENANT_ENDPOINTS_LIST_INVITATIONS = Operation(
    'api_v1_tenant_endpoints_list_invitations', 'get', '/api/v1/tenant/invitations')
API_V1_TENANT_ENDPOINTS_LIST_INVOICES = Operation(
    'api_v1_tenant_endpoints_list_invoices', 'get', '/api/v1/tenant/invoices')
API_V1_TENANT_ENDPOINTS_LIST_MEMBERS = Operation(
    'api_v1_tenant_endpoints_list_members', 'get', '/api/v1/tenant/members')
API_V1_TENANT_ENDPOINTS_REMOVE_MEMBER = Operation(
    'api_v1_tenant_endpoints_remove_member',
    'delete',
    '/api/v1/tenant/members/{member_id}')
API_V1_TENANT_ENDPOINTS_REVOKE_API_KEY = Operation(
    'api_v1_tenant_endpoints_revoke_api_key',
    'delete',
    '/api/v1/tenant/api-keys/{key_id}')
API_V1_TENANT_ENDPOINTS_REVOKE_INVITATION = Operation(
    'api_v1_tenant_endpoints_revoke_invitation',
    'delete',
    '/api/v1/tenant/invitations/{invitation_id}')
API_V1_TENANT_ENDPOINTS_ROTATE_API_KEY = Operation(
    'api_v1_tenant_endpoints_rotate_api_key',
    'post',
    '/api/v1/tenant/api-keys/{key_id}/rotate')
API_V1_TENANT_ENDPOINTS_UPDATE_MEMBER_ROLE = Operation(
    'api_v1_tenant_endpoints_update_member_role',
    'patch',
    '/api/v1/tenant/members/{member_id}')
API_V1_TENANT_ENDPOINTS_UPDATE_TENANT_CONFIG = Operation(
    'api_v1_tenant_endpoints_update_tenant_config', 'patch', '/api/v1/tenant/config')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_CREATE_WEBHOOK_CONFIG = Operation(
    'apps_platform_events_api_webhook_endpoints_create_webhook_config',
    'post',
    '/api/v1/webhooks/configs')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_DELETE_WEBHOOK_CONFIG = Operation(
    'apps_platform_events_api_webhook_endpoints_delete_webhook_config',
    'delete',
    '/api/v1/webhooks/configs/{config_id}')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_LIST_WEBHOOK_CONFIGS = Operation(
    'apps_platform_events_api_webhook_endpoints_list_webhook_configs',
    'get',
    '/api/v1/webhooks/configs')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_LIST_WEBHOOK_DELIVERIES = Operation(
    'apps_platform_events_api_webhook_endpoints_list_webhook_deliveries',
    'get',
    '/api/v1/webhooks/configs/{config_id}/deliveries')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_ROTATE_WEBHOOK_SECRET = Operation(
    'apps_platform_events_api_webhook_endpoints_rotate_webhook_secret',
    'post',
    '/api/v1/webhooks/configs/{config_id}/rotate-secret')
APPS_PLATFORM_EVENTS_API_WEBHOOK_ENDPOINTS_UPDATE_WEBHOOK_CONFIG = Operation(
    'apps_platform_events_api_webhook_endpoints_update_webhook_config',
    'patch',
    '/api/v1/webhooks/configs/{config_id}')
APPS_REFERRALS_API_ENDPOINTS_ANALYTICS_EARNINGS = Operation(
    'apps_referrals_api_endpoints_analytics_earnings',
    'get',
    '/api/v1/referrals/analytics/earnings')
APPS_REFERRALS_API_ENDPOINTS_ANALYTICS_SUMMARY = Operation(
    'apps_referrals_api_endpoints_analytics_summary',
    'get',
    '/api/v1/referrals/analytics/summary')
APPS_REFERRALS_API_ENDPOINTS_ATTRIBUTE_REFERRAL = Operation(
    'apps_referrals_api_endpoints_attribute_referral',
    'post',
    '/api/v1/referrals/attribute')
APPS_REFERRALS_API_ENDPOINTS_CREATE_PROGRAM = Operation(
    'apps_referrals_api_endpoints_create_program', 'post', '/api/v1/referrals/program')
APPS_REFERRALS_API_ENDPOINTS_DEACTIVATE_PROGRAM = Operation(
    'apps_referrals_api_endpoints_deactivate_program',
    'delete',
    '/api/v1/referrals/program')
APPS_REFERRALS_API_ENDPOINTS_GET_PROGRAM = Operation(
    'apps_referrals_api_endpoints_get_program', 'get', '/api/v1/referrals/program')
APPS_REFERRALS_API_ENDPOINTS_GET_REFERRAL_LEDGER = Operation(
    'apps_referrals_api_endpoints_get_referral_ledger',
    'get',
    '/api/v1/referrals/referrals/{referral_id}/ledger')
APPS_REFERRALS_API_ENDPOINTS_GET_REFERRER = Operation(
    'apps_referrals_api_endpoints_get_referrer',
    'get',
    '/api/v1/referrals/referrers/{customer_id}')
APPS_REFERRALS_API_ENDPOINTS_GET_REFERRER_EARNINGS = Operation(
    'apps_referrals_api_endpoints_get_referrer_earnings',
    'get',
    '/api/v1/referrals/referrers/{customer_id}/earnings')
APPS_REFERRALS_API_ENDPOINTS_GET_REFERRER_REFERRALS = Operation(
    'apps_referrals_api_endpoints_get_referrer_referrals',
    'get',
    '/api/v1/referrals/referrers/{customer_id}/referrals')
APPS_REFERRALS_API_ENDPOINTS_LIST_REFERRERS = Operation(
    'apps_referrals_api_endpoints_list_referrers', 'get', '/api/v1/referrals/referrers')
APPS_REFERRALS_API_ENDPOINTS_PAYOUT_EXPORT = Operation(
    'apps_referrals_api_endpoints_payout_export',
    'get',
    '/api/v1/referrals/payouts/export')
APPS_REFERRALS_API_ENDPOINTS_REACTIVATE_PROGRAM = Operation(
    'apps_referrals_api_endpoints_reactivate_program',
    'post',
    '/api/v1/referrals/program/reactivate')
APPS_REFERRALS_API_ENDPOINTS_REGISTER_REFERRER = Operation(
    'apps_referrals_api_endpoints_register_referrer',
    'post',
    '/api/v1/referrals/referrers')
APPS_REFERRALS_API_ENDPOINTS_REVOKE_REFERRAL = Operation(
    'apps_referrals_api_endpoints_revoke_referral',
    'delete',
    '/api/v1/referrals/referrals/{referral_id}')
APPS_REFERRALS_API_ENDPOINTS_UPDATE_PROGRAM = Operation(
    'apps_referrals_api_endpoints_update_program', 'patch', '/api/v1/referrals/program')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_CANCEL_SUBSCRIPTION = Operation(
    'apps_subscriptions_api_endpoints_cancel_subscription',
    'post',
    '/api/v1/subscriptions/customers/{external_id}/subscription/cancel')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_GET_INVOICES = Operation(
    'apps_subscriptions_api_endpoints_get_invoices',
    'get',
    '/api/v1/subscriptions/customers/{customer_id}/invoices')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_GET_SUBSCRIPTION = Operation(
    'apps_subscriptions_api_endpoints_get_subscription',
    'get',
    '/api/v1/subscriptions/customers/{customer_id}/subscription')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_PAUSE_SUBSCRIPTION = Operation(
    'apps_subscriptions_api_endpoints_pause_subscription',
    'post',
    '/api/v1/subscriptions/customers/{external_id}/subscription/pause')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_RESUME_SUBSCRIPTION = Operation(
    'apps_subscriptions_api_endpoints_resume_subscription',
    'post',
    '/api/v1/subscriptions/customers/{external_id}/subscription/resume')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_SET_CUSTOMER_SEATS = Operation(
    'apps_subscriptions_api_endpoints_set_customer_seats',
    'post',
    '/api/v1/subscriptions/customers/{external_id}/seats')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_SUBSCRIBE_CUSTOMER = Operation(
    'apps_subscriptions_api_endpoints_subscribe_customer',
    'post',
    '/api/v1/subscriptions/customers/{external_id}/subscribe')
APPS_SUBSCRIPTIONS_API_ENDPOINTS_TRIGGER_SYNC = Operation(
    'apps_subscriptions_api_endpoints_trigger_sync',
    'post',
    '/api/v1/subscriptions/sync')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_BUSINESS_MARGIN = Operation(
    'apps_subscriptions_api_margin_endpoints_business_margin',
    'get',
    '/api/v1/margin/business/{external_id}')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_CUSTOMER_MARGIN = Operation(
    'apps_subscriptions_api_margin_endpoints_customer_margin',
    'get',
    '/api/v1/margin/customers/{customer_id}')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_GET_REVENUE = Operation(
    'apps_subscriptions_api_margin_endpoints_get_revenue',
    'get',
    '/api/v1/margin/customers/{customer_id}/revenue')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_GET_REVENUE_MODE = Operation(
    'apps_subscriptions_api_margin_endpoints_get_revenue_mode',
    'get',
    '/api/v1/margin/customers/{customer_id}/revenue-mode')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_GET_THRESHOLD = Operation(
    'apps_subscriptions_api_margin_endpoints_get_threshold',
    'get',
    '/api/v1/margin/threshold')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_LIST_MARGIN = Operation(
    'apps_subscriptions_api_margin_endpoints_list_margin',
    'get',
    '/api/v1/margin/customers')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_BY_DIMENSION = Operation(
    'apps_subscriptions_api_margin_endpoints_margin_by_dimension',
    'get',
    '/api/v1/margin/by-dimension')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_SUMMARY = Operation(
    'apps_subscriptions_api_margin_endpoints_margin_summary',
    'get',
    '/api/v1/margin/summary')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_TREND = Operation(
    'apps_subscriptions_api_margin_endpoints_margin_trend',
    'get',
    '/api/v1/margin/customers/{customer_id}/trend')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_MARGIN_UNPROFITABLE = Operation(
    'apps_subscriptions_api_margin_endpoints_margin_unprofitable',
    'get',
    '/api/v1/margin/unprofitable')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_PUT_REVENUE = Operation(
    'apps_subscriptions_api_margin_endpoints_put_revenue',
    'put',
    '/api/v1/margin/customers/{customer_id}/revenue')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_PUT_REVENUE_MODE = Operation(
    'apps_subscriptions_api_margin_endpoints_put_revenue_mode',
    'put',
    '/api/v1/margin/customers/{customer_id}/revenue-mode')
APPS_SUBSCRIPTIONS_API_MARGIN_ENDPOINTS_PUT_THRESHOLD = Operation(
    'apps_subscriptions_api_margin_endpoints_put_threshold',
    'put',
    '/api/v1/margin/threshold')

# --- routes the contract does not publish ------------------------------------
#
# The debts gates/migration-ledger.yaml carries against G17:
# routes that exist in no spec and no router, called by methods slice 4 removes.
# Each name is derived from the `found` the ledger excuses, so the constant and
# the excuse cannot drift apart.

UNPUBLISHED_GET_METERING_PRICING_RATE_CARDS_HISTORY = Operation(
    None, 'get', '/api/v1/metering/pricing/rate-cards/{}/history')
UNPUBLISHED_POST_METERING_PRICING_RATE_CARDS_BATCH = Operation(
    None, 'post', '/api/v1/metering/pricing/rate-cards/batch')
UNPUBLISHED_PUT_METERING_PRICING_RATE_CARDS = Operation(
    None, 'put', '/api/v1/metering/pricing/rate-cards/{}')
