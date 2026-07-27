import { z } from "zod";

/** Comma-separated non-negative ints, e.g. "50, 80, 100". Blank = none. */
const alertLevelsField = z
  .string()
  .refine(
    (v) =>
      v.trim() === "" ||
      v
        .split(",")
        .every((p) => /^\d+$/.test(p.trim()) && p.trim() !== ""),
    "Comma-separated whole numbers only (e.g. 50, 80, 100)",
  );

export function parseAlertLevels(raw: string): number[] {
  return raw
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p !== "")
    .map((p) => Number(p));
}

export const budgetSchema = z.object({
  cap: z.number().nonnegative("Cap can't be negative"),
  enforceMode: z.enum(["alert_only", "blocking"]),
  hardStopPct: z
    .number()
    .int("Whole number")
    .min(0, "0–1000")
    .max(1000, "0–1000"),
  alertLevels: alertLevelsField,
  failClosed: z.boolean(),
});
export type BudgetFormValues = z.infer<typeof budgetSchema>;

export const postpaidSchema = z.object({
  groupBy: z.string(),
  consolidateWithSubscription: z.boolean(),
});
export type PostpaidFormValues = z.infer<typeof postpaidSchema>;

export const creditSchema = z.object({
  customerId: z.string().min(1, "Customer is required"),
  amount: z.number().positive("Amount must be greater than 0"),
  source: z.string().min(1, "Source is required"),
  reference: z.string().min(1, "Reference is required"),
  reasonCode: z.string(),
  actor: z.string(),
});
export type CreditFormValues = z.infer<typeof creditSchema>;

export const debitSchema = z.object({
  customerId: z.string().min(1, "Customer is required"),
  amount: z.number().positive("Amount must be greater than 0"),
  reference: z.string().min(1, "Reference is required"),
  allowNegative: z.boolean(),
  reasonCode: z.string(),
  actor: z.string(),
});
export type DebitFormValues = z.infer<typeof debitSchema>;

export const preCheckSchema = z.object({
  customerId: z.string().min(1, "Customer is required"),
  startTask: z.boolean(),
  externalTaskId: z.string(),
  providerCostLimit: z
    .number()
    .nonnegative("Can't be negative")
    .optional(),
});
export type PreCheckFormValues = z.infer<typeof preCheckSchema>;
