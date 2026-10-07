export type PlanDemo = {
  id: EntityId;
  name: string;
  price: number;
  days: number | null;
  lessons: number | null;
  isActive: boolean;
  usageMode?: "attendance" | "scheduled" | "period";
  absentRule?: "consume" | "dont_consume" | "choice";
  excusedRule?: "consume" | "dont_consume" | "makeup";
  endRule?: "lessons" | "date" | "whichever_first";
};

export type PaymentDemo = {
  id: EntityId;
  studentId: EntityId;
  planId: EntityId;
  subscriptionId?: EntityId;
  amount: number;
  adjustedAmount: number;
  paidAmount: number;
  refundedAmount: number;
  balanceAmount: number;
  creditAmount: number;
  dueDate: string;
  status: "pending" | "paid" | "overdue" | "refunded" | "cancelled";
  method?: "Картка" | "Готівка" | "Переказ";
};

export function paymentMethodLabel(method: string | null | undefined): PaymentDemo["method"] {
  const labels: Record<string, PaymentDemo["method"]> = {
    cash: "Готівка",
    card: "Картка",
    bank: "Переказ",
    other: "Переказ",
  };
  return method ? labels[method] : undefined;
}

