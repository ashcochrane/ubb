import * as React from "react";
import { Users } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useHasRole } from "@/hooks/use-current-role";
import { ROLES, memberStatusLabel, roleLabel } from "@/lib/labels";
import { formatShortDate } from "@/lib/format";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { useMembers, useRemoveMember, useUpdateMemberRole } from "../api/queries";
import type { Member } from "../api/types";

export function MembersSection() {
  const isAdmin = useHasRole("admin");
  const members = useMembers();
  const roleMutation = useUpdateMemberRole();
  const removeMutation = useRemoveMember();
  const [mutatingId, setMutatingId] = React.useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = React.useState<Member | null>(null);

  const changeRole = (member: Member, role: string) => {
    if (role === member.role) return;
    setMutatingId(member.id);
    roleMutation.mutate(
      { memberId: member.id, role },
      {
        onSuccess: () =>
          toastSuccess(`${member.email} is now ${roleLabel(role)}`),
        onError: toastOnError("Couldn't change the role"),
        onSettled: () => setMutatingId(null),
      },
    );
  };

  const confirmRemove = () => {
    if (!removeTarget) return;
    const target = removeTarget;
    removeMutation.mutate(target.id, {
      onSuccess: () => {
        setRemoveTarget(null);
        toastSuccess(`${target.email} was removed`);
      },
      onError: (error) => {
        setRemoveTarget(null);
        toastOnError("Couldn't remove the member")(error);
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>
          Everyone with access to this workspace. Read can view, Write can
          record usage and run day-to-day operations, Admin can change
          configuration and move money.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {members.isInitialLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : members.isError ? (
          <ErrorCard
            error={members.error}
            onRetry={() => void members.refetch()}
          />
        ) : members.rows.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No members yet"
            description="Invite teammates below — they get access on their first sign-in."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Added</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {members.rows.map((member) => (
                    <TableRow key={member.id}>
                      <TableCell className="font-medium">
                        {member.email}
                      </TableCell>
                      <TableCell>
                        <DisabledHint
                          disabled={!isAdmin}
                          hint="Requires the Admin role."
                        >
                          <Select
                            value={member.role}
                            onValueChange={(role: string | null) => {
                              if (role !== null) changeRole(member, role);
                            }}
                          >
                            <SelectTrigger
                              size="sm"
                              aria-label={`Role for ${member.email}`}
                              disabled={!isAdmin || mutatingId === member.id}
                              className="w-[110px]"
                            >
                              <SelectValue>
                                {mutatingId === member.id
                                  ? "Working…"
                                  : roleLabel(member.role)}
                              </SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              {ROLES.map((role) => (
                                <SelectItem key={role} value={role}>
                                  {roleLabel(role)}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </DisabledHint>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            member.status === "active" ? "secondary" : "outline"
                          }
                        >
                          {memberStatusLabel(member.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatShortDate(member.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <DisabledHint
                          disabled={!isAdmin}
                          hint="Requires the Admin role."
                        >
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            disabled={!isAdmin || removeMutation.isPending}
                            onClick={() => setRemoveTarget(member)}
                          >
                            Remove
                          </Button>
                        </DisabledHint>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <LoadMore
              shownCount={members.rows.length}
              hasMore={members.hasMore}
              isFetchingNextPage={members.isFetchingNextPage}
              onLoadMore={members.fetchNextPage}
              noun="members"
            />
          </>
        )}
        {!isAdmin && (
          <p className="mt-3 text-[12px] text-muted-foreground">
            Changing roles or removing members requires the Admin role.
          </p>
        )}
      </CardContent>

      <ConfirmDialog
        open={removeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRemoveTarget(null);
        }}
        title="Remove member?"
        description={
          removeTarget
            ? `${removeTarget.email} loses access immediately. Their history stays in the audit ledger, and you can invite them again later.`
            : ""
        }
        confirmLabel="Remove"
        destructive
        pending={removeMutation.isPending}
        onConfirm={confirmRemove}
      />
    </Card>
  );
}
