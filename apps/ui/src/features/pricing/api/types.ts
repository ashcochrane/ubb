import type { MeteringSchemas } from "@/api/types";

/** A rate card ("book") — a versioned set of provider rates. */
export type Book = MeteringSchemas["BookOut"];
export type BookInput = MeteringSchemas["BookIn"];

/** A single provider rate inside a rate card. */
export type Rate = MeteringSchemas["RateOut"];
export type RateInput = MeteringSchemas["RateIn"];

/** A staged rate change submitted when publishing a new rate-card version. */
export type RateChange = MeteringSchemas["RateChangeIn"];
export type PublishInput = MeteringSchemas["PublishIn"];

/** Tenant default markup applied on top of provider cost. */
export type TenantMarkup = MeteringSchemas["TenantMarkupOut"];
export type TenantMarkupInput = MeteringSchemas["TenantMarkupIn"];
