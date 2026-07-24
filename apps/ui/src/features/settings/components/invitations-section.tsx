import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailPlus } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
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
import { Input } from "@/components/ui/input";
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
import { ROLES, invitationStatusLabel, roleLabel } from "@/lib/labels";
import { formatShortDate } from "@/lib/format";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import {
  useCreateInvitation,
  useInvitations,
  useRevokeInvitation,
} from "../api/queries";
import type { Invitation } from "../api/types";

const inviteSchema = z.object({
  email: z.email("Enter a valid email address"),
  role: z.string().min(1),
});

type InviteValues = z.infer<typeof inviteSchema>;

export function InvitationsSection() {
  const invitations = useInvitations({ enabled: true });
  const create = useCreateInvitation();
  const revoke = useRevokeInvitation();
  const [revokeTarget, setRevokeTarget] = React.useState<Invitation | null>(
    null,
  );

  const form = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role: "read" },
  });
  const role = form.watch("role");

  const sendInvite = (values: InviteValues) => {
    create.mutate(values, {
      onSuccess: (invitation) => {
        form.reset({ email: "", role: values.role });
        toastSuccess(`Invitation sent to ${invitation.email}`);
      },
    });
  };

  const confirmRevoke = () => {
    if (!revokeTarget) return;
    const target = revokeTarget;
    revoke.mutate(target.id, {
      onSuccess: () => {
        setRevokeTarget(null);
        toastSuccess(`Invitation for ${target.email} revoked`);
      },
      onError: (error) => {
        setRevokeTarget(null);
        toastOnError("Couldn't revoke the invitation")(error);
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>
          Invited teammates get access on their first sign-in with the invited
          email — they show up as Pending members until then.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(event) => void form.handleSubmit(sendInvite)(event)}
          className="flex flex-col gap-2 sm:flex-row sm:items-start"
          noValidate
        >
          <div className="flex-1">
            <Input
              type="email"
              placeholder="teammate@company.com"
              aria-label="Email to invite"
              {...form.register("email")}
            />
            {form.formState.errors.email && (
              <p className="mt-1 text-xs text-destructive">
                {form.formState.errors.email.message}
              </p>
            )}
          </div>
          <Select
            value={role}
            onValueChange={(value: string | null) => {
              if (value !== null) {
                form.setValue("role", value, { shouldDirty: true });
              }
            }}
          >
            <SelectTrigger aria-label="Role for the invite" className="w-[110px]">
              <SelectValue>{roleLabel(role)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {roleLabel(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Working…" : "Send invite"}
          </Button>
        </form>
        {create.isError && (
          <p className="text-xs text-destructive">
            {problemMessage(create.error)}
          </p>
        )}

        {invitations.isInitialLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : invitations.isError ? (
          <ErrorCard
            error={invitations.error}
            onRetry={() => void invitations.refetch()}
          />
        ) : invitations.rows.length === 0 ? (
          <EmptyState
            icon={MailPlus}
            title="No invitations yet"
            description="Send the first invite above to bring a teammate in."
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
                    <TableHead>Sent</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invitations.rows.map((invitation) => (
                    <TableRow key={invitation.id}>
                      <TableCell className="font-medium">
                        {invitation.email}
                      </TableCell>
                      <TableCell>{roleLabel(invitation.role)}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            invitation.status === "pending"
                              ? "secondary"
                              : "outline"
                          }
                        >
                          {invitationStatusLabel(invitation.status)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatShortDate(invitation.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {invitation.status === "pending" ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            disabled={revoke.isPending}
                            onClick={() => setRevokeTarget(invitation)}
                          >
                            Revoke
                          </Button>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <LoadMore
              shownCount={invitations.rows.length}
              hasMore={invitations.hasMore}
              isFetchingNextPage={invitations.isFetchingNextPage}
              onLoadMore={invitations.fetchNextPage}
              noun="invitations"
            />
          </>
        )}
      </CardContent>

      <ConfirmDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
        title="Revoke invitation?"
        description={
          revokeTarget
            ? `${revokeTarget.email} won't be able to join with this invitation. If they already accepted, remove the member instead.`
            : ""
        }
        confirmLabel="Revoke"
        destructive
        pending={revoke.isPending}
        onConfirm={confirmRevoke}
      />
    </Card>
  );
}
