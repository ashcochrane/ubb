import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { UserPlus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { FormField } from "@/components/shared/form-field";
import { useCreateInvitation } from "../api/queries";
import { inviteSchema, type InviteValues } from "../lib/schema";
import { ROLES } from "./roles";

export function InviteMemberDialog() {
  const [open, setOpen] = useState(false);
  const invite = useCreateInvitation();
  const form = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role: "member" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    await invite.mutateAsync(values);
    setOpen(false);
    form.reset({ email: "", role: "member" });
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) form.reset({ email: "", role: "member" });
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm">
            <UserPlus />
            Invite
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Invite a teammate</DialogTitle>
            <DialogDescription>
              They activate on first sign-in with the email you enter here.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex flex-col gap-4">
            <FormField label="Email" error={form.formState.errors.email?.message}>
              {(id) => (
                <Input id={id} type="email" placeholder="teammate@company.com" {...form.register("email")} />
              )}
            </FormField>
            <FormField label="Role" error={form.formState.errors.role?.message}>
              {(id) => (
                <Controller
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id={id} className="w-full">
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
                  )}
                />
              )}
            </FormField>
          </div>
          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={invite.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={invite.isPending}>
              {invite.isPending ? "Sending…" : "Send invitation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
