# Billing and payment rules

Status: implemented baseline  
Scope: `crm/`  
Branch: `crm-v1`

## Core model

For the current CRM stage, `Payment` is a **charge / amount due**, not a bank transaction ledger.

A normal paid study period is:

1. Create a `StudentSubscription` for a concrete period.
2. Create its linked `Payment` charge in the same database transaction.
3. The charge stays `pending` until money is confirmed.
4. When money is confirmed, the charge becomes `paid`.

Use `POST /billing/charges` for normal subscription billing. It atomically creates both records so an orphan subscription cannot remain if charge creation fails.

## Charge identity and duplicate protection

A subscription charge is treated as duplicate when the same organization, student, plan and `starts_on` already has a non-cancelled subscription.

The backend rejects the duplicate with HTTP 409.

This is the baseline idempotency rule for manual billing. A future automatic recurring-billing job should use the same period identity (or an explicit billing-period key) rather than relying on UI state.

## Due date

Every subscription charge must be remindable.

When `due_date` is omitted from `POST /billing/charges`, backend uses `starts_on` as the due date.

Ad-hoc `POST /payments` can still have no due date, because not every manual financial record requires collection reminders.

## Payment states

Allowed normal transitions:

```text
pending -> paid
pending -> cancelled
paid    -> refunded   (dedicated refund flow is not implemented yet)
```

Rules:

- only `pending` can be marked paid;
- a paid charge cannot be marked paid again;
- only `pending` can be cancelled;
- cancelling a charge created with a subscription also cancels that linked subscription;
- cancelled/refunded charges never count as outstanding debt;
- do not delete financial history to fix mistakes.

`overdue` is intentionally **derived**, not stored as a PaymentStatus:

```text
status == pending AND due_date < today
```

This prevents stale "overdue" flags after a charge is paid.

## Group/student billing state

For an individual student:

- `overdue`: at least one pending charge is past due;
- `due`: at least one pending charge is due today;
- `upcoming`: pending charge exists, but it is not past due;
- `current`: no pending charge and the latest active subscription has not ended;
- `no_plan`: none of the above.

`amount_due_minor` is the total of all pending charges.

`next_due_date` is the earliest dated pending charge.

Never invent a future payment date when no next charge exists. If a current subscription has no future charge yet, UI should show that there is no created next charge, not pretend a payment is scheduled.

## Reminder algorithm

Reminders are generated only for `pending` charges with a due date.

Stages:

| Relative to due date | Stage |
| --- | --- |
| 3–1 days before | `upcoming_3` |
| due date | `due_today` |
| 1–2 days overdue | `overdue_1` |
| 3–6 days overdue | `overdue_3` |
| 7–13 days overdue | `overdue_7` |
| 14–29 days overdue | `overdue_14` |
| 30+ days overdue | `overdue_30` |

Only the **current stage** is offered to staff.

After the staff member records that the reminder was handled, `PaymentReminder` stores the payment + stage. The unique constraint on `(payment_id, stage)` prevents duplicate reminders for the same stage.

A later stage can still appear if the charge remains unpaid.

When a charge becomes paid/cancelled/refunded, it immediately drops out of the reminder queue.

## Reminder channels

Current implementation records manual follow-up channels:

- manual;
- phone;
- sms;
- email;
- messenger.

The current CRM UI uses a phone action and records that the call was made.

Recording a reminder is **not** the same as sending an SMS/email. Future integrations must record success only after the external provider confirms acceptance.

For automatic delivery, use an outbox/job worker instead of sending provider requests inside the HTTP request that changes billing data.

## Group detail

`GET /groups/{group_id}/detail` aggregates the operational information needed when opening a group:

- group and recurring schedule;
- active/paused members;
- parent/contact;
- enrollment date;
- attendance counts and attendance rate;
- subscription plan;
- outstanding amount;
- next due date;
- last payment;
- payment history.

Role behavior:

- owner/admin/manager/accountant can see billing information;
- teacher can see assigned-group roster and attendance information, but billing is hidden;
- tenant boundaries remain enforced.

## Corrections and refunds

Current safe correction for a mistaken unpaid charge:

1. cancel the pending charge;
2. linked subscription is cancelled too;
3. keep both records for audit/history;
4. create the corrected charge.

Do not overwrite a paid charge or cancel it as if money was never received.

A dedicated refund/credit-note flow should be implemented before live payment-provider integration. It should retain the original payment and record refund amount, reason, timestamp and actor.

## Recurring billing

Automatic creation of the next monthly charge is **not yet implemented**.

Before enabling it, add an idempotent recurring-billing service that:

- finds subscriptions/renewals requiring the next period;
- creates at most one charge per billing period;
- respects paused/cancelled students;
- does not create charges after enrollment has finished;
- supports discounts deliberately rather than copying them accidentally;
- records an audit event;
- can safely retry after a crash.

Until then, staff creates the next subscription/charge manually and the reminder engine works against those created charges.

## Future payment-provider integration

LiqPay/WayForPay/other provider integration should keep these layers separate:

1. CRM charge (`Payment`) — what the family owes.
2. Provider payment attempt — external checkout/payment intent.
3. Provider transaction — confirmed money movement.
4. Refund/adjustment — reverse money movement.

Provider webhooks must be idempotent and must never trust only a browser redirect as proof of payment.
