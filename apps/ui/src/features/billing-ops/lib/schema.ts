import { z } from "zod";

export const topUpSchema = z.object({
  amount: z.number().positive("Amount must be greater than 0"),
});
export type TopUpFormValues = z.infer<typeof topUpSchema>;

export const withdrawSchema = z.object({
  amount: z.number().positive("Amount must be greater than 0"),
  description: z.string(),
});
export type WithdrawFormValues = z.infer<typeof withdrawSchema>;

export const autoTopUpSchema = z.object({
  isEnabled: z.boolean(),
  threshold: z.number().min(0),
  topUpAmount: z.number().positive(),
});
export type AutoTopUpFormValues = z.infer<typeof autoTopUpSchema>;
