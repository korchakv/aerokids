import type { Dispatch, SetStateAction } from "react";
import type { ApiPaymentWorkspaceItem, ApiStudentSubscription, OperationsBundle } from "../../api";
import type { LocationDemo } from "../locations/types";
import type { PaymentDemo, PlanDemo } from "../billing/model";
import { paymentMethodLabel } from "../billing/model";
import type { StaffDemo } from "../staff/model";
import { staffRoleLabel } from "../staff/model";

export function applyOperations(
  bundle: OperationsBundle,
  setLocations: Dispatch<SetStateAction<LocationDemo[]>>,
  setStaff: Dispatch<SetStateAction<StaffDemo[]>>,
  setPlans: Dispatch<SetStateAction<PlanDemo[]>>,
  setPayments: Dispatch<SetStateAction<PaymentDemo[]>>,
  setSubscriptions: Dispatch<SetStateAction<ApiStudentSubscription[]>>,
) {
  setLocations(bundle.locations.map((item) => ({
    id: item.id,
    name: item.name,
    address: item.address ?? "",
    isActive: item.is_active,
  })));

  setStaff(bundle.staff.map((item) => ({
    id: item.id,
    fullName: item.full_name,
    role: staffRoleLabel(item.role),
    canTeach: item.can_teach,
    email: item.email ?? "",
    phone: item.phone ?? "",
    locationIds: item.assignments.location_ids,
    groupIds: item.assignments.group_ids,
    isActive: item.is_active,
  })));

  setPlans(bundle.plans.map((item) => ({
    id: item.id,
    name: item.name,
    price: item.price_minor / 100,
    days: item.period_days,
    lessons: item.lessons_included,
    isActive: item.is_active,
    usageMode: item.usage_mode,
    absentRule: item.absent_rule,
    excusedRule: item.excused_rule,
    endRule: item.end_rule,
  })));

  const today = new Date().toISOString().slice(0, 10);
  setPayments(bundle.payments.map((item) => ({
    id: item.id,
    studentId: item.student_id,
    planId: item.plan_id ?? "",
    subscriptionId: item.subscription_id ?? undefined,
    amount: item.amount_minor / 100,
    adjustedAmount: item.adjusted_amount_minor / 100,
    paidAmount: item.paid_minor / 100,
    refundedAmount: item.refunded_minor / 100,
    balanceAmount: item.balance_minor / 100,
    creditAmount: item.credit_minor / 100,
    dueDate: item.due_date ?? "",
    status: item.status === "pending" && item.due_date && item.due_date < today ? "overdue" : item.status,
    method: paymentMethodLabel(item.method),
  })));
  setSubscriptions(bundle.subscriptions);
}

export function paymentPageItemToDemo(item: ApiPaymentWorkspaceItem): PaymentDemo {
  const today = new Date().toISOString().slice(0, 10);
  return {
    id: item.id,
    studentId: item.student_id,
    planId: item.plan_id ?? "",
    subscriptionId: item.subscription_id ?? undefined,
    amount: item.amount_minor / 100,
    adjustedAmount: item.adjusted_amount_minor / 100,
    paidAmount: item.paid_minor / 100,
    refundedAmount: item.refunded_minor / 100,
    balanceAmount: item.balance_minor / 100,
    creditAmount: item.credit_minor / 100,
    dueDate: item.due_date ?? "",
    status: item.status === "pending" && item.due_date && item.due_date < today ? "overdue" : item.status,
    studentName: item.student_name,
    studentPhone: item.student_phone ?? undefined,
    contactName: item.contact_name ?? undefined,
    contactPhone: item.contact_phone ?? undefined,
    planName: item.plan_name ?? undefined,
  };
}

