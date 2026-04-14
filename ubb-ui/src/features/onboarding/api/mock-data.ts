import type { StripeCustomer } from "./types";

export const mockStripeCustomers: StripeCustomer[] = [
  { name: "Acme Corp", stripeId: "cus_R4kB9xPm2nQ", email: "billing@acmecorp.com", internalSlug: "acme_corp", metadataKey: "acme_corp", revenue30d: 2400 },
  { name: "BrightPath Ltd", stripeId: "cus_Q7mN3vHj8wL", email: "finance@brightpath.co", internalSlug: "brightpath", metadataKey: "brightpath", revenue30d: 1800 },
  { name: "NovaTech Inc", stripeId: "cus_S2pK5tRn7xY", email: "accounts@novatech.io", internalSlug: "novatech", metadataKey: "novatech", revenue30d: 950 },
  { name: "Helios Digital", stripeId: "cus_U6nR2wKm9xQ", email: "ap@heliosdigital.com", internalSlug: "helios", metadataKey: "helios", revenue30d: 720 },
  { name: "ClearView Analytics", stripeId: "cus_V3bP8sHn5mJ", email: "pay@clearview.ai", internalSlug: "clearview", metadataKey: "clearview", revenue30d: 150 },
  { name: "Eko Systems", stripeId: "cus_W1cT4rFk7pN", email: null, internalSlug: null, metadataKey: null, revenue30d: 90 },
];
