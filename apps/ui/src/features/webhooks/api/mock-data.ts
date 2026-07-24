// Mock fixtures — one coherent story for Acme AI, July 2026:
// - a production endpoint on a curated event list, with a realistic mix of
//   successful, HTTP-failed, and connection-failed deliveries;
// - an ops endpoint subscribed to all events ("*") mid secret-rotation
//   (retiring_secret_expires_at set);
// - a freshly added, PAUSED staging endpoint with zero deliveries
//   (the deliveries empty state).
// Configs and deliveries are newest-first, matching the cursor contract.

import type { WebhookConfig, WebhookDelivery } from "./types";

export const MOCK_WEBHOOK_CONFIGS: WebhookConfig[] = [
  {
    id: "c91d2f64-7b3a-42e8-9f15-2d8ab64c0e37",
    url: "https://staging.acme.dev/hooks/ubb",
    event_types: ["usage.recorded"],
    is_active: false,
    retiring_secret_expires_at: null,
    created_at: "2026-07-18T09:24:00Z",
  },
  {
    id: "8d24f9b1-4c1e-4f7a-b02d-93a5e6c8d410",
    url: "https://ops.acme.dev/ubb/events",
    event_types: ["*"],
    is_active: true,
    retiring_secret_expires_at: "2026-07-25T09:00:00Z",
    created_at: "2026-06-02T16:40:00Z",
  },
  {
    id: "3f6c1a52-9d0e-4b6a-8a3d-6a1f0c9b2e71",
    url: "https://api.acme.dev/webhooks/ubb",
    event_types: [
      "billing.balance_low",
      "billing.balance_critical",
      "stop.fired",
      "stop.cleared",
    ],
    is_active: true,
    retiring_secret_expires_at: null,
    created_at: "2026-05-11T11:05:00Z",
  },
];

export const MOCK_WEBHOOK_DELIVERIES: Record<string, WebhookDelivery[]> = {
  "3f6c1a52-9d0e-4b6a-8a3d-6a1f0c9b2e71": [
    {
      id: "0d3e5a71-2f48-4c1b-9e6d-8b1a4c7f2d90",
      event_id: "9c1f4b82-6a3d-4e7f-b510-27d8e9a6c143",
      event_type: "billing.balance_low",
      success: true,
      status_code: 200,
      error_message: "",
      created_at: "2026-07-23T14:12:00Z",
    },
    {
      id: "1e4f6b82-3a59-4d2c-8f7e-9c2b5d8a3e01",
      event_id: "a2d05c93-7b4e-4f80-a621-38e9f0b7d254",
      event_type: "stop.fired",
      success: false,
      status_code: 500,
      error_message: "Receiver answered 500 Internal Server Error",
      created_at: "2026-07-23T13:58:00Z",
    },
    {
      id: "2f507c93-4b60-4e3d-a08f-0d3c6e9b4f12",
      event_id: "b3e16da4-8c5f-4091-b732-49f0a1c8e365",
      event_type: "stop.cleared",
      success: false,
      status_code: null,
      error_message:
        "Connection to api.acme.dev timed out after 10s (attempt 3 of 5). The endpoint did not accept the TCP connection; the delivery will be retried on the backoff schedule until the retry horizon is reached.",
      created_at: "2026-07-22T03:31:00Z",
    },
    {
      id: "30618da4-5c71-4f4e-b19a-1e4d70ac5023",
      event_id: "c4f27eb5-9d60-41a2-c843-5a01b2d9f476",
      event_type: "billing.balance_critical",
      success: true,
      status_code: 200,
      error_message: "",
      created_at: "2026-07-21T19:47:00Z",
    },
    {
      id: "41729eb5-6d82-4059-c2ab-2f5e81bd6134",
      event_id: "d5038fc6-ae71-42b3-d954-6b12c3e0a587",
      event_type: "billing.balance_low",
      success: false,
      status_code: 429,
      error_message: "Receiver answered 429 Too Many Requests",
      created_at: "2026-07-20T08:15:00Z",
    },
    {
      id: "5283afc6-7e93-416a-d3bc-306192ce7245",
      event_id: "e61490d7-bf82-43c4-ea65-7c23d4f1b698",
      event_type: "stop.fired",
      success: true,
      status_code: 200,
      error_message: "",
      created_at: "2026-07-19T22:03:00Z",
    },
  ],
  "8d24f9b1-4c1e-4f7a-b02d-93a5e6c8d410": [
    {
      id: "6394b0d7-8fa4-427b-e4cd-4172a3df8356",
      event_id: "f725a1e8-c093-44d5-fb76-8d34e5a2c709",
      event_type: "usage.recorded",
      success: true,
      status_code: 200,
      error_message: "",
      created_at: "2026-07-23T15:02:00Z",
    },
    {
      id: "74a5c1e8-90b5-438c-f5de-5283b4ea9467",
      event_id: "0836b2f9-d1a4-45e6-0c87-9e45f6b3d810",
      event_type: "tenant.api_key_rotated",
      success: true,
      status_code: 204,
      error_message: "",
      created_at: "2026-07-22T10:19:00Z",
    },
    {
      id: "85b6d2f9-a1c6-449d-06ef-6394c5fb0578",
      event_id: "1947c30a-e2b5-46f7-1d98-af5607c4e921",
      event_type: "sandbox.reset_completed",
      success: true,
      status_code: 200,
      error_message: "",
      created_at: "2026-07-21T07:44:00Z",
    },
  ],
  // Paused staging endpoint — no deliveries yet.
  "c91d2f64-7b3a-42e8-9f15-2d8ab64c0e37": [],
};
