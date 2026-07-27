import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQuery } from "../test-utils";
import { TeamPage } from "./team-page";

describe("TeamPage", () => {
  it("renders the members roster and invitations from mock data", async () => {
    renderWithQuery(<TeamPage />);

    // Members
    expect(await screen.findByText("mia@acme.ai")).toBeInTheDocument();
    expect(screen.getByText("sasha@acme.ai")).toBeInTheDocument();
    // rob appears in the roster AND as an accepted invitation.
    expect(screen.getAllByText("rob@acme.ai").length).toBeGreaterThanOrEqual(1);

    // Invitations (admin section) — revoked history is visible too
    expect(
      await screen.findByText("contractor@freelance.dev"),
    ).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();

    // Activation explanation
    expect(
      screen.getByText(/first sign-in with the invited email/),
    ).toBeInTheDocument();
  });

  it("creates an invitation and shows the new pending teammate", async () => {
    renderWithQuery(<TeamPage />);
    await screen.findByText("mia@acme.ai");

    fireEvent.change(screen.getByLabelText("Email to invite"), {
      target: { value: "newbie@acme.ai" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));

    // Appears in the invitations list (and as a pending member).
    const matches = await screen.findAllByText("newbie@acme.ai");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("rejects inviting an existing member with the server's message", async () => {
    renderWithQuery(<TeamPage />);
    await screen.findByText("mia@acme.ai");

    fireEvent.change(screen.getByLabelText("Email to invite"), {
      target: { value: "mia@acme.ai" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));

    expect(
      await screen.findByText(/already a member or has a pending invitation/),
    ).toBeInTheDocument();
  });
});
