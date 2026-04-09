interface RouteErrorProps {
  error: Error;
}

export function RouteError({ error }: RouteErrorProps) {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center gap-3 p-8">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        onClick={() => window.location.reload()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Reload page
      </button>
    </div>
  );
}
