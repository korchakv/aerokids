import { UiIcon } from "../../components/UiIcon";
import type { ApiPaymentReminder, ApiStudentSubscription } from "../../api";
import type { EntityId, Lead } from "../leads/model";
import type { PaymentDemo, PlanDemo } from "./model";

type PaymentTotals = {
  paid: number;
  pending: number;
  overdue: number;
};

type PaymentCounts = { paid: number; pending: number; overdue: number };
type PaymentStatusFilter = "all" | "pending" | "paid" | "refunded" | "cancelled";
type PaymentOverdueFilter = "all" | "yes" | "no";

type PaymentsViewProps = {
  payments: PaymentDemo[];
  plans: PlanDemo[];
  subscriptions: ApiStudentSubscription[];
  leads: Lead[];
  paymentTotals: PaymentTotals;
  paymentCounts: PaymentCounts;
  query: string;
  statusFilter: PaymentStatusFilter;
  overdueFilter: PaymentOverdueFilter;
  sort: "newest" | "due" | "student";
  pageTotal: number;
  pageLimit: number;
  pageOffset: number;
  loading: boolean;
  error: string;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: PaymentStatusFilter) => void;
  onOverdueFilterChange: (value: PaymentOverdueFilter) => void;
  onSortChange: (value: "newest" | "due" | "student") => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  paymentReminders: ApiPaymentReminder[];
  reminderSavingId: EntityId | null;
  focusedPaymentId: EntityId | null;
  canManagePlans: boolean;
  showInactivePlans: boolean;
  money: (value: number) => string;
  formatPhone: (value: string) => string;
  onReminderHandled: (reminder: ApiPaymentReminder) => void;
  onOpenPaymentForm: () => void;
  onMarkPaymentPaid: (paymentId: EntityId) => void;
  onOpenPaymentAction: (payment: PaymentDemo, type: "partial" | "refund" | "adjustment") => void;
  onToggleAutoRenew: (subscriptionId: EntityId, next: boolean) => void;
  onOpenPlanChange: (subscriptionId: EntityId) => void;
  onResumeSubscription: (subscriptionId: EntityId) => void;
  onPauseSubscription: (subscriptionId: EntityId) => void;
  onOpenPlanCreate: () => void;
  onOpenPlanEdit: (plan: PlanDemo) => void | Promise<void>;
  onToggleInactivePlans: () => void;
};

export function PaymentsView({
  payments,
  plans,
  subscriptions,
  leads,
  paymentTotals,
  paymentCounts,
  query,
  statusFilter,
  overdueFilter,
  sort,
  pageTotal,
  pageLimit,
  pageOffset,
  loading,
  error,
  onQueryChange,
  onStatusFilterChange,
  onOverdueFilterChange,
  onSortChange,
  onPreviousPage,
  onNextPage,
  paymentReminders,
  reminderSavingId,
  focusedPaymentId,
  canManagePlans,
  showInactivePlans,
  money,
  formatPhone,
  onReminderHandled,
  onOpenPaymentForm,
  onMarkPaymentPaid,
  onOpenPaymentAction,
  onToggleAutoRenew,
  onOpenPlanChange,
  onResumeSubscription,
  onPauseSubscription,
  onOpenPlanCreate,
  onOpenPlanEdit,
  onToggleInactivePlans,
}: PaymentsViewProps) {
  const activePlans = plans.filter((plan) => plan.isActive);
  const inactivePlans = plans.filter((plan) => !plan.isActive);

  return <section className="paymentsLayout" data-testid="payments-workspace">
    <div className="paymentsMain">
      <section className="paymentStats">
        <article><span>Сплачено</span><strong>{money(paymentTotals.paid)}</strong><small>{paymentCounts.paid} платежів</small></article>
        <article><span>Очікується</span><strong>{money(paymentTotals.pending)}</strong><small>{paymentCounts.pending} рахунків</small></article>
        <article><span>Прострочено</span><strong>{money(paymentTotals.overdue)}</strong><small>{paymentCounts.overdue} боргів</small></article>
      </section>

      {paymentReminders.length > 0 && <article className="panel reminderPanel">
        <div className="panelHead"><div><p className="eyebrow">Контроль оплат</p><h2>Потрібно нагадати</h2></div><span className="counter">{paymentReminders.length}</span></div>
        <p className="reminderIntro">CRM показує лише актуальний етап нагадування. Після фіксації дзвінка цей етап зникає і не дублюється; наступне нагадування з’явиться лише на наступному етапі прострочення.</p>
        <div className="reminderList">{paymentReminders.map((reminder) => <div className="reminderRow" key={reminder.payment_id + reminder.stage}>
          <div><b>{reminder.student_name}</b><small>{reminder.contact_name ?? "Контакт не вказано"}{reminder.contact_phone ? " · " + reminder.contact_phone : ""}</small></div>
          <span><b>{money(reminder.amount_minor / 100)}</b><small>до {new Date(reminder.due_date + "T00:00:00").toLocaleDateString("uk-UA")}</small></span>
          <span className={"reminderStage " + (reminder.days_from_due > 0 ? "overdue" : "upcoming")}>{reminder.label}</span>
          <div className="reminderActions">{reminder.contact_phone && <a className="link" href={"tel:" + reminder.contact_phone.replace(/\s/g, "")}>Подзвонити</a>}<button className="search" disabled={reminderSavingId === reminder.payment_id} onClick={() => onReminderHandled(reminder)}>{reminderSavingId === reminder.payment_id ? "Зберігаємо…" : "Дзвінок зроблено"}</button></div>
        </div>)}</div>
      </article>}

      <article className="panel paymentsPanel">
        <div className="panelHead"><div><p className="eyebrow">Фінанси</p><h2>Оплати учнів</h2></div><button className="primary" onClick={onOpenPaymentForm}>+ Нарахування</button></div>
        <div className="paymentRegistryControls">
          <label className="registrySearch"><span>Пошук</span><input data-testid="payments-search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Учень, контакт або примітка" /></label>
          <label className="candidateSelect">Статус<select value={statusFilter} onChange={(event) => onStatusFilterChange(event.target.value as PaymentStatusFilter)}>
            <option value="all">Усі</option><option value="pending">Очікується</option><option value="paid">Сплачено</option><option value="refunded">Повернено</option><option value="cancelled">Скасовано</option>
          </select></label>
          <label className="candidateSelect">Прострочення<select value={overdueFilter} onChange={(event) => onOverdueFilterChange(event.target.value as PaymentOverdueFilter)}>
            <option value="all">Усі</option><option value="yes">Прострочені</option><option value="no">Без прострочення</option>
          </select></label>
          <label className="candidateSelect">Сортування<select value={sort} onChange={(event) => onSortChange(event.target.value as "newest" | "due" | "student")}>
            <option value="newest">Найновіші</option><option value="due">За датою оплати</option><option value="student">За учнем</option>
          </select></label>
        </div>
        {error && <div className="registryError" role="alert">{error}</div>}
        <div className={"paymentTable " + (loading ? "registryLoading" : "")}>
          <div className="paymentRow paymentHead"><span>Дитина / відповідальний</span><span>Абонемент</span><span>Нараховано / залишок</span><span>До дати</span><span>Статус</span><span>Дії</span></div>
          {!loading && payments.length === 0 && <div className="emptyState">{query.trim() || statusFilter !== "all" || overdueFilter !== "all" ? "За цим фільтром оплат не знайдено." : "Оплат поки немає."}</div>}
          {loading && payments.length === 0 && <div className="emptyState">Завантаження оплат…</div>}
          {payments.map((payment) => {
            const student = leads.find((lead) => lead.id === payment.studentId);
            const plan = plans.find((item) => item.id === payment.planId);
            const subscription = payment.subscriptionId ? subscriptions.find((item) => item.id === payment.subscriptionId) : undefined;
            const statusLabel = payment.status === "paid" ? "Сплачено" : payment.status === "overdue" ? "Прострочено" : payment.status === "refunded" ? "Повернено" : payment.status === "cancelled" ? "Скасовано" : "Очікується";
            const studentName = payment.studentName ?? student?.child ?? "Учень";
            const studentPhone = payment.studentPhone ?? student?.childPhone;
            const contactName = payment.contactName ?? student?.parent ?? "Не вказано";
            const contactPhone = payment.contactPhone ?? student?.phone;
            return <div id={"payment-" + payment.id} className={"paymentRow " + (focusedPaymentId === payment.id ? "paymentFocused" : "")} key={payment.id}>
              <span className="paymentIdentity"><b>{studentName}</b><small>Дитина{studentPhone ? " · " + formatPhone(studentPhone) : ""}</small><small><strong>Відповідальний:</strong> {contactName}{contactPhone ? " · " + formatPhone(contactPhone) : ""}</small></span>
              <span className="paymentPlanCell"><b>{payment.planName ?? plan?.name ?? "—"}{plan && !plan.isActive ? <em className="inactivePlanInline">Неактивний</em> : null}</b>{subscription && <small>{subscription.status === "paused" ? "Пауза" : subscription.auto_renew ? "Автопродовження увімкнено" : "Без автопродовження"}</small>}</span>
              <span className="paymentAmountCell"><b>{money(payment.adjustedAmount)}</b><small>{payment.balanceAmount > 0 ? <>Залишок: {money(payment.balanceAmount)}</> : payment.creditAmount > 0 ? <>Кредит: {money(payment.creditAmount)}</> : <>Внесено: {money(Math.max(0, payment.paidAmount - payment.refundedAmount))}</>}{payment.refundedAmount > 0 ? " · повернено " + money(payment.refundedAmount) : ""}</small>{payment.creditAmount > 0 && <em className="paymentCreditHint">Буде враховано в наступному періоді</em>}</span>
              <span>{payment.dueDate ? new Date(payment.dueDate + "T00:00:00").toLocaleDateString("uk-UA") : "—"}</span>
              <span className={"paymentStatus " + payment.status}>{statusLabel}</span>
              <span className="paymentActions">
                {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link payAction" onClick={() => onMarkPaymentPaid(payment.id)}>Сплатити повністю</button>}
                {payment.balanceAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => onOpenPaymentAction(payment, "partial")}>Часткова</button>}
                {payment.paidAmount - payment.refundedAmount > 0 && payment.status !== "cancelled" && <button className="link" onClick={() => onOpenPaymentAction(payment, "refund")}>Повернення</button>}
                {payment.status !== "cancelled" && <button className="link" onClick={() => onOpenPaymentAction(payment, "adjustment")}>Коригувати</button>}
                {subscription && subscription.status !== "cancelled" && <button className="link" onClick={() => onToggleAutoRenew(subscription.id, !subscription.auto_renew)}>{subscription.auto_renew ? "Вимкнути авто" : "Увімкнути авто"}</button>}
                {subscription && ["active", "paused"].includes(subscription.status) && plans.some((item) => item.isActive && item.id !== subscription.plan_id) && <button className="link" onClick={() => onOpenPlanChange(subscription.id)}>Змінити тариф зараз</button>}
                {subscription?.status === "paused" ? <button className="link" onClick={() => onResumeSubscription(subscription.id)}>Відновити</button> : subscription && subscription.status === "active" ? <button className="link" onClick={() => onPauseSubscription(subscription.id)}>Пауза</button> : null}
              </span>
            </div>;
          })}
        </div>
        <div className="registryPager" aria-label="Сторінки оплат">
          <span>{pageTotal === 0 ? "0" : `${pageOffset + 1}–${Math.min(pageOffset + pageLimit, pageTotal)}`} з {pageTotal}</span>
          <div><button disabled={loading || pageOffset === 0} onClick={onPreviousPage}>← Назад</button><button disabled={loading || pageOffset + pageLimit >= pageTotal} onClick={onNextPage}>Далі →</button></div>
        </div>
      </article>
    </div>

    <aside className="paymentsSide">
      <article className="panel tariffPanel">
        <div className="panelHead"><div><p className="eyebrow">Тарифи</p><h2>Абонементи</h2></div><div className="miniActions"><span className="counter">{activePlans.length}</span>{canManagePlans && <button className="link" onClick={onOpenPlanCreate}>+ Тариф</button>}</div></div>
        <div className="planCards">
          {activePlans.map((plan) => <div className="planCard tariffCard" key={plan.id}>
            <div><b>{plan.name}</b><span>{[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відвідувань" : ""].filter(Boolean).join(" · ")}</span></div>
            <div className="tariffCardRight"><strong>{plan.price ? money(plan.price) : "Індивідуально"}</strong>{canManagePlans && <button className="tariffEditButton" type="button" title="Редагувати тариф" aria-label={"Редагувати " + plan.name} onClick={() => void onOpenPlanEdit(plan)}><UiIcon name="edit" size={13} /></button>}</div>
          </div>)}
          {activePlans.length === 0 && <div className="emptyState compactEmpty">Активних тарифів немає.</div>}
        </div>
        {inactivePlans.length > 0 && <div className="inactiveTariffs">
          <button className="inactiveTariffsToggle" type="button" onClick={onToggleInactivePlans}><span>Неактивні</span><small>{inactivePlans.length}</small><i>{showInactivePlans ? "↑" : "↓"}</i></button>
          {showInactivePlans && <div className="planCards inactivePlanCards">{inactivePlans.map((plan) => <div className="planCard tariffCard inactive" key={plan.id}>
            <div><b>{plan.name}<em>Неактивний</em></b><span>{[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відвідувань" : ""].filter(Boolean).join(" · ")}</span></div>
            <div className="tariffCardRight"><strong>{plan.price ? money(plan.price) : "Індивідуально"}</strong>{canManagePlans && <button className="tariffEditButton" type="button" title="Редагувати тариф" aria-label={"Редагувати " + plan.name} onClick={() => void onOpenPlanEdit(plan)}><UiIcon name="edit" size={13} /></button>}</div>
          </div>)}</div>}
        </div>}
      </article>
      <article className="panel financeHint"><p className="eyebrow">MVP</p><h2>Що вже враховано</h2><p>Оплата зберігається окремо від абонемента. Це дозволить пізніше підключити LiqPay, WayForPay чи інший еквайринг без зміни ядра.</p></article>
    </aside>
  </section>;
}
