import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  return (
    <div>
      <h1>UBB Dashboard</h1>
      <p>Welcome to the Usage-Based Billing dashboard.</p>
    </div>
  );
}
