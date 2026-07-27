import { z } from "zod";

/** Dollar input → non-negative number. RHF `valueAsNumber` gives NaN when blank. */
const dollars = z
  .number({ error: "Enter an amount" })
  .min(0, "Must be zero or more");

/** Optional dollar input: blank (undefined via setValueAs) means "leave unchanged". */
const optionalDollars = dollars.optional();

export const createPlanSchema = z.object({
  key: z.string().trim().min(1, "Key is required"),
  name: z.string().trim().min(1, "Name is required"),
  accessFee: dollars,
  perSeat: dollars,
  interval: z.enum(["month", "year"]),
});

export type CreatePlanFormValues = z.infer<typeof createPlanSchema>;

export const updatePlanSchema = z
  .object({
    key: z.string().trim().min(1, "Key is required"),
    accessFee: optionalDollars,
    perSeat: optionalDollars,
    migrateExisting: z.boolean(),
  })
  .refine((v) => v.accessFee !== undefined || v.perSeat !== undefined, {
    message: "Set a new access fee, a new per-seat price, or both",
    path: ["accessFee"],
  });

export type UpdatePlanFormValues = z.infer<typeof updatePlanSchema>;

export const customerLookupSchema = z.object({
  customerId: z.string().trim().min(1, "Customer ID is required"),
});

export type CustomerLookupFormValues = z.infer<typeof customerLookupSchema>;
