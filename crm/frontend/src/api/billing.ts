import type { ApiPaymentReminder, Session } from "./types";
import { apiGet, apiPost } from "./client";

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
