import { Trash2, Users, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Section, LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatShortDate } from "@/lib/format";
import {
  useMembers,
  useInvitations,
  useUpdateMemberRole,
  useRemoveMember,
  useRevokeInvitation,
} from "../api/queries";
import { InviteMemberDialog } from "./invite-member-dialog";
import { ROLES } from "./roles";

export function TeamTab() {
  return (
    <div className="space-y-6">
      <MembersSection />
      <InvitationsSection />
    </div>
  );
}

function MembersSection() {
  const pager = useMembers();
  const updateRole = useUpdateMemberRole();
  const remove = useRemoveMember();

  return (
    <Section title="Members" description="People with access to this tenant.">
      {pager.isLoading ? (
        <LoadingRows />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState icon={Users} title="No members yet" description="Invite a teammate to get started." />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((member) => (
                <TableRow key={member.id}>
                  <TableCell className="font-medium">{member.email}</TableCell>
                  <TableCell>
                    <Select
                      value={member.role}
                      onValueChange={(role) => {
                        if (role && role !== member.role) {
                          updateRole.mutate({ memberId: member.id, body: { role } });
                        }
                      }}
                    >
                      <SelectTrigger size="sm" className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => (
                          <SelectItem key={r.value} value={r.value}>
                            {r.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={member.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {member.activated_at ? formatShortDate(member.activated_at) : "—"}
                  </TableCell>
                  <TableCell>
                    <ConfirmDialog
                      destructive
                      title="Remove this member?"
                      description={`${member.email} will lose access to this tenant immediately.`}
                      confirmLabel="Remove member"
                      onConfirm={async () => {
                        await remove.mutateAsync(member.id);
                      }}
                      trigger={
                        <Button variant="ghost" size="icon-sm" aria-label="Remove member">
                          <Trash2 />
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </Section>
  );
}

function InvitationsSection() {
  const pager = useInvitations();
  const revoke = useRevokeInvitation();

  return (
    <Section
      title="Invitations"
      description="Pending and past invitations."
      actions={<InviteMemberDialog />}
    >
      {pager.isLoading ? (
        <LoadingRows rows={3} />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState icon={Mail} title="No invitations" description="Invite a teammate to add them to this tenant." />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((inv) => (
                <TableRow key={inv.id}>
                  <TableCell className="font-medium">{inv.email}</TableCell>
                  <TableCell>
                    <StatusBadge value={inv.role} tone="neutral" />
                  </TableCell>
                  <TableCell>
                    <StatusBadge value={inv.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatShortDate(inv.created_at)}
                  </TableCell>
                  <TableCell>
                    <ConfirmDialog
                      destructive
                      title="Revoke this invitation?"
                      description={`The invite to ${inv.email} will no longer be valid.`}
                      confirmLabel="Revoke invitation"
                      onConfirm={async () => {
                        await revoke.mutateAsync(inv.id);
                      }}
                      trigger={
                        <Button variant="ghost" size="icon-sm" aria-label="Revoke invitation">
                          <Trash2 />
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </Section>
  );
}
