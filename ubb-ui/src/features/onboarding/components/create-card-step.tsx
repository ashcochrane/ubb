import { NewCardWizard } from "@/features/pricing-cards/components/new-card-wizard";

interface Props {
  onSuccess: () => void;
  onSkip: () => void;
}

export function CreateCardStep({ onSuccess, onSkip }: Props) {
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Create your first pricing card</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Pricing cards describe what you're tracking. You can skip this for now and add one later.
        </p>
      </div>
      <NewCardWizard onSuccess={() => onSuccess()} onSkip={onSkip} />
    </div>
  );
}
