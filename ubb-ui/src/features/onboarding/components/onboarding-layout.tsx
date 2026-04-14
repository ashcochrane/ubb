import type { ReactNode } from "react";

interface OnboardingLayoutProps {
  children: ReactNode;
}

export function OnboardingLayout({ children }: OnboardingLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="mx-auto w-full max-w-[640px] px-6 py-8">
        <div className="mb-8 text-lg font-bold tracking-tight">UBB</div>
        {children}
      </div>
    </div>
  );
}
