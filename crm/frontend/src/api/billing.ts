import type { ApiPaymentPage, ApiPaymentReminder, Session } from "./types";
import { apiGet, apiPost } from "./client";

export type PaymentPageOptions = {
  q?: string;
  status?: "pending" | "paid" | "refunded" | "cancelled";
  overdue?: boolean;
  sort?: "newest" | "due" | "student";
  limit?: number;
  offset?: number;
};

export function loadPaymentPage(session: Session, options: PaymentPageOptions = {}) {
  const params = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return apiGet<ApiPaymentPage>(`/payments/page${query ? `?${query}` : ""}`, session);
}

export function runBillingRenewals(session: Session) {
  return apiPost<{
    resumed_subscriptions: number;
    created_subscriptions: number;
    skipped_stale_subscriptions: number;
    created_payment_ids: string[];
  }>("/billing/renewals/run", {}, session);
}

export function loadPaymentReminders(session: Session) {
  return apiGet<ApiPaymentReminder[]>("/payment-reminders", session);
}

export function recordPaymentReminder(
  paymentId: string,
  stage: ApiPaymentReminder["stage"],
  channel: "manual" | "sms" | "email" | "messenger" | "phone",
  session: Session,
) {
  return apiPost(`/payments/${paymentId}/reminders`, { stage, channel }, session);
}
