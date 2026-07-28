// Zod schemas for the small referral forms (register referrer, attribute a
// referral). The attribute contract does NOT enforce "exactly one of
// code | link_token" — the form does, by construction: the user picks ONE
// method and only that field is ever sent.

import { z } from "zod";

import type { AttributeRequest } from "../api/types";

export const registerReferrerSchema = z.object({
  customer_id: z.uuid("Enter a valid UBB customer UUID"),
});

export type RegisterReferrerValues = z.infer<typeof registerReferrerSchema>;

export const ATTRIBUTION_METHODS = ["code", "link_token"] as const;
export type AttributionMethod = (typeof ATTRIBUTION_METHODS)[number];

export function isAttributionMethod(value: string): value is AttributionMethod {
  return (ATTRIBUTION_METHODS as readonly string[]).includes(value);
}

export const attributeFormSchema = z
  .object({
    customer_id: z.uuid("Enter a valid UBB customer UUID"),
    method: z.enum(ATTRIBUTION_METHODS),
    code: z.string(),
    link_token: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.method === "code" && values.code.trim() === "") {
      ctx.addIssue({ code: "custom", path: ["code"], message: "Enter the referral code" });
    }
    if (values.method === "link_token" && values.link_token.trim() === "") {
      ctx.addIssue({
        code: "custom",
        path: ["link_token"],
        message: "Enter the referral link token",
      });
    }
  });

export type AttributeFormValues = z.infer<typeof attributeFormSchema>;

/** Builds the API body with EXACTLY ONE of code | link_token set. */
export function toAttributeRequest(values: AttributeFormValues): AttributeRequest {
  if (values.method === "code") {
    return { customer_id: values.customer_id, code: values.code.trim(), link_token: null };
  }
  return { customer_id: values.customer_id, code: null, link_token: values.link_token.trim() };
}
