import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">UBB Dashboard</h1>
      <p className="text-muted-foreground mb-4">
        Welcome to the Usage-Based Billing dashboard.
      </p>
      <Button>It works</Button>
    </div>
  );
}
