"""Membership service-layer logic (identity build 1, #79): invite, revoke, and
first-login activation, exercised without HTTP or Clerk (claims are passed as a
plain dict, the same shape ``verify_member_token`` returns)."""
from django.test import TestCase

from apps.platform.events.models import OutboxEvent
from apps.platform.membership import services
from apps.platform.membership.models import (
    ACTIVE,
    INV_ACCEPTED,
    INV_PENDING,
    INV_REVOKED,
    PENDING,
    Invitation,
    Member,
)
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant
from core.problems import Problem


class InviteMemberTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def test_invite_creates_invitation_and_pending_member_and_event(self):
        inv = services.invite_member(self.tenant, "Sam@Example.com", WRITE)
        self.assertEqual(inv.status, INV_PENDING)
        self.assertEqual(inv.email, "sam@example.com")  # normalized
        self.assertEqual(inv.role, WRITE)
        member = Member.objects.get(tenant=self.tenant, email="sam@example.com")
        self.assertEqual(member.status, PENDING)
        self.assertEqual(member.role, WRITE)
        self.assertEqual(member.invitation_id, inv.id)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="invitation.created", tenant_id=self.tenant.id).exists())

    def test_invite_duplicate_pending_is_conflict(self):
        services.invite_member(self.tenant, "sam@example.com", READ)
        with self.assertRaises(Problem) as ctx:
            services.invite_member(self.tenant, "sam@example.com", READ)
        self.assertEqual(ctx.exception.code, "conflict")

    def test_invite_active_member_is_conflict(self):
        services.invite_member(self.tenant, "sam@example.com", READ)
        services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        with self.assertRaises(Problem) as ctx:
            services.invite_member(self.tenant, "sam@example.com", ADMIN)
        self.assertEqual(ctx.exception.code, "conflict")

    def test_invite_bad_role_rejected(self):
        with self.assertRaises(Problem) as ctx:
            services.invite_member(self.tenant, "sam@example.com", "owner")
        self.assertEqual(ctx.exception.code, "validation_error")

    def test_same_email_different_tenants_allowed(self):
        other = Tenant.objects.create(name="Beta")
        services.invite_member(self.tenant, "sam@example.com", READ)
        # No conflict across tenants — the unique key is (tenant, email).
        services.invite_member(other, "sam@example.com", ADMIN)
        self.assertEqual(Member.objects.filter(email="sam@example.com").count(), 2)


class RevokeInvitationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def test_revoke_pending_drops_member_and_emits_event(self):
        inv = services.invite_member(self.tenant, "sam@example.com", READ)
        services.revoke_invitation(self.tenant, inv.id)
        inv.refresh_from_db()
        self.assertEqual(inv.status, INV_REVOKED)
        self.assertFalse(
            Member.objects.filter(tenant=self.tenant, email="sam@example.com").exists())
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="invitation.revoked", tenant_id=self.tenant.id).exists())

    def test_revoke_is_idempotent(self):
        inv = services.invite_member(self.tenant, "sam@example.com", READ)
        services.revoke_invitation(self.tenant, inv.id)
        # Second revoke: no error, no second event.
        services.revoke_invitation(self.tenant, inv.id)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="invitation.revoked").count(), 1)

    def test_revoke_unknown_is_404(self):
        import uuid
        with self.assertRaises(Problem) as ctx:
            services.revoke_invitation(self.tenant, uuid.uuid4())
        self.assertEqual(ctx.exception.code, "not_found")

    def test_revoke_accepted_is_conflict(self):
        inv = services.invite_member(self.tenant, "sam@example.com", READ)
        services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        inv.refresh_from_db()
        self.assertEqual(inv.status, INV_ACCEPTED)
        with self.assertRaises(Problem) as ctx:
            services.revoke_invitation(self.tenant, inv.id)
        self.assertEqual(ctx.exception.code, "conflict")

    def test_revoke_prevents_activation(self):
        inv = services.invite_member(self.tenant, "sam@example.com", READ)
        services.revoke_invitation(self.tenant, inv.id)
        principal = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        self.assertIsNone(principal)


class ResolveMemberTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme")

    def test_first_login_activates_pending_member(self):
        inv = services.invite_member(self.tenant, "sam@example.com", WRITE)
        principal = services.resolve_member_for_claims(
            {"sub": "user_clerk_1", "email": "sam@example.com"})
        self.assertIsNotNone(principal)
        self.assertEqual(principal.status, ACTIVE)
        self.assertEqual(principal.clerk_user_id, "user_clerk_1")
        self.assertIsNotNone(principal.activated_at)
        self.assertEqual(principal.tenant_id, self.tenant.id)
        self.assertEqual(principal.role, WRITE)
        inv.refresh_from_db()
        self.assertEqual(inv.status, INV_ACCEPTED)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="member.activated", tenant_id=self.tenant.id).exists())

    def test_returning_member_matches_by_sub_no_new_event(self):
        services.invite_member(self.tenant, "sam@example.com", READ)
        services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        # Second call: already active, matched by sub, no second activation event.
        principal = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        self.assertIsNotNone(principal)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="member.activated").count(), 1)

    def test_email_matching_is_case_insensitive(self):
        services.invite_member(self.tenant, "Sam@Example.com", READ)
        principal = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.COM"})
        self.assertIsNotNone(principal)

    def test_unknown_user_is_none(self):
        self.assertIsNone(services.resolve_member_for_claims(
            {"sub": "nobody", "email": "ghost@example.com"}))

    def test_no_sub_is_none(self):
        services.invite_member(self.tenant, "sam@example.com", READ)
        self.assertIsNone(services.resolve_member_for_claims(
            {"email": "sam@example.com"}))

    def test_multi_tenant_pending_is_ambiguous_and_left_pending(self):
        other = Tenant.objects.create(name="Beta")
        services.invite_member(self.tenant, "sam@example.com", READ)
        services.invite_member(other, "sam@example.com", ADMIN)
        # Two pending invites for the same email, no tenant selector => refuse
        # rather than guess, and leave BOTH pending for build 2 (never activate
        # into an unusable two-active state).
        principal = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        self.assertIsNone(principal)
        self.assertEqual(
            Member.objects.filter(email="sam@example.com", status=ACTIVE).count(), 0)
        self.assertEqual(
            Member.objects.filter(email="sam@example.com", status=PENDING).count(), 2)

    def test_later_second_invite_never_breaks_a_working_principal(self):
        # Reviewer's sharp edge: a member with a working single-tenant login must
        # not be locked out when later invited to a second tenant.
        other = Tenant.objects.create(name="Beta")
        services.invite_member(self.tenant, "sam@example.com", READ)
        first = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        self.assertIsNotNone(first)
        # Now invited to a second tenant.
        services.invite_member(other, "sam@example.com", ADMIN)
        # Next login still resolves to the original working membership.
        again = services.resolve_member_for_claims(
            {"sub": "user_1", "email": "sam@example.com"})
        self.assertIsNotNone(again)
        self.assertEqual(again.id, first.id)
        self.assertEqual(again.tenant_id, self.tenant.id)
        # The second-tenant membership stays pending (activates in build 2).
        second = Member.objects.get(tenant=other, email="sam@example.com")
        self.assertEqual(second.status, "pending")
