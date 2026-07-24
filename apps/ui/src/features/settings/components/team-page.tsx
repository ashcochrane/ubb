import { useHasRole } from "@/hooks/use-current-role";

import { InvitationsSection } from "./invitations-section";
import { MembersSection } from "./members-section";

export function TeamPage() {
  // UI gating only (fail-open): the invitations list is the one Admin-gated
  // GET. If the role guess is wrong the section still handles its 403.
  const isAdmin = useHasRole("admin");

  return (
    <div className="max-w-4xl space-y-6">
      <MembersSection />
      {isAdmin && <InvitationsSection />}
    </div>
  );
}
