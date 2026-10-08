import type { ApiAuditEvent, ApiStudentSubscription } from "../../api";
import type { EntityId, Lead } from "../leads/model";
import type { PlanDemo } from "./model";

type PaymentActionType = "partial" | "refund" | "adjustment";
type PaymentMethod = "cash" | "card" | "bank";
type AdjustmentDirection = "decrease" | "increase";

type BillingDialogsProps = {
  plans: PlanDemo[];
  subscriptions: ApiStudentSubscription[];
  activeStudents: Lead[];
  money: (value: number) => string;
  paymentMinDate: string;

  showPlanForm: boolean;
  planEditId: EntityId | null;
  planName: string;
  planPrice: string;
  planDays: string;
  planLessons: string;
  planActive: boolean;
  planSaving: boolean;
  planHistory: ApiAuditEvent[];
  planHistoryLoading: boolean;
  planHistoryOpen: boolean;
  tariffHistoryDetail: (event: ApiAuditEvent) => string;
  onClosePlanForm: () => void;
  onPlanNameChange: (value: string) => void;
  onPlanPriceChange: (value: string) => void;
  onPlanDaysChange: (value: string) => void;
  onPlanLessonsChange: (value: string) => void;
  onPlanActiveChange: (value: boolean) => void;
  onSavePlan: () => void | Promise<void>;
  onTogglePlanHistory: () => void | Promise<void>;

  showPaymentForm: boolean;
  paymentStudentId: EntityId;
  paymentPlanId: EntityId;
  paymentDueDate: string;
  paymentAutoRenew: boolean;
  paymentSaving: boolean;
  onClosePaymentForm: () => void;
  onPaymentStudentChange: (value: EntityId) => void;
  onPaymentPlanChange: (value: EntityId) => void;
  onPaymentDueDateChange: (value: string) => void;
  onPaymentAutoRenewChange: (value: boolean) => void;
  onCreatePayment: () => void | Promise<void>;

  paymentActionId: EntityId | null;
  paymentActionType: PaymentActionType | null;
  paymentActionAmount: string;
  paymentActionReason: string;
  paymentActionMethod: PaymentMethod;
  paymentAdjustmentDirection: AdjustmentDirection;
  paymentActionSaving: boolean;
  onClosePaymentAction: () => void;
  onPaymentActionAmountChange: (value: string) => void;
  onPaymentActionReasonChange: (value: string) => void;
  onPaymentActionMethodChange: (value: PaymentMethod) => void;
  onPaymentAdjustmentDirectionChange: (value: AdjustmentDirection) => void;
  onSubmitPaymentAction: () => void | Promise<void>;

  planChangeSubscriptionId: EntityId | null;
  planChangePlanId: EntityId | "";
  planChangeReason: string;
  planChangeSaving: boolean;
  planChangeResult: string;
  onClosePlanChange: () => void;
  onPlanChangePlanIdChange: (value: EntityId | "") => void;
  onPlanChangeReasonChange: (value: string) => void;
  onSubmitPlanChange: () => void | Promise<void>;

  pauseSubscriptionId: EntityId | null;
  pauseStart: string;
  pauseResumeOn: string;
  pauseNote: string;
  onClosePause: () => void;
  onPauseStartChange: (value: string) => void;
  onPauseResumeOnChange: (value: string) => void;
  onPauseNoteChange: (value: string) => void;
  onSubmitPause: () => void | Promise<void>;
};

function digitsOnly(value: string): string {
  return value.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
}

export function BillingDialogs({
  plans,
  subscriptions,
  activeStudents,
  money,
  paymentMinDate,
  showPlanForm,
  planEditId,
  planName,
  planPrice,
  planDays,
  planLessons,
  planActive,
  planSaving,
  planHistory,
  planHistoryLoading,
  planHistoryOpen,
  tariffHistoryDetail,
  onClosePlanForm,
  onPlanNameChange,
  onPlanPriceChange,
  onPlanDaysChange,
  onPlanLessonsChange,
  onPlanActiveChange,
  onSavePlan,
  onTogglePlanHistory,
  showPaymentForm,
  paymentStudentId,
  paymentPlanId,
  paymentDueDate,
  paymentAutoRenew,
  paymentSaving,
  onClosePaymentForm,
  onPaymentStudentChange,
  onPaymentPlanChange,
  onPaymentDueDateChange,
  onPaymentAutoRenewChange,
  onCreatePayment,
  paymentActionId,
  paymentActionType,
  paymentActionAmount,
  paymentActionReason,
  paymentActionMethod,
  paymentAdjustmentDirection,
  paymentActionSaving,
  onClosePaymentAction,
  onPaymentActionAmountChange,
  onPaymentActionReasonChange,
  onPaymentActionMethodChange,
  onPaymentAdjustmentDirectionChange,
  onSubmitPaymentAction,
  planChangeSubscriptionId,
  planChangePlanId,
  planChangeReason,
  planChangeSaving,
  planChangeResult,
  onClosePlanChange,
  onPlanChangePlanIdChange,
  onPlanChangeReasonChange,
  onSubmitPlanChange,
  pauseSubscriptionId,
  pauseStart,
  pauseResumeOn,
  pauseNote,
  onClosePause,
  onPauseStartChange,
  onPauseResumeOnChange,
  onPauseNoteChange,
  onSubmitPause,
}: BillingDialogsProps) {
  const pricedActivePlans = plans.filter((plan) => plan.isActive && plan.price > 0);

  return <>
    {showPlanForm && <div className="modalBackdrop" data-testid="plan-dialog">
      <div className="groupModal tariffEditModal" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" onClick={onClosePlanForm}>×</button>
        <p className="eyebrow">Тарифи</p><h2>{planEditId ? "Редагувати тариф" : "Новий тариф"}</h2>
        <p className="modalIntro">Тариф — шаблон для нових і наступних періодів. Уже створені абонементи зберігають свої умови до завершення.</p>
        <label>Назва<input value={planName} onChange={(event) => onPlanNameChange(event.target.value)} placeholder="8 занять / 30 днів" /></label>
        <div className="formTwo">
          <label>Ціна, грн<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="2000" value={planPrice} onChange={(event) => onPlanPriceChange(digitsOnly(event.target.value))} /></label>
          <label>Днів<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="30" value={planDays} onChange={(event) => onPlanDaysChange(digitsOnly(event.target.value))} /><small className="fieldHint">Можна залишити порожнім, якщо обмеження тільки за відвідуваннями.</small></label>
        </div>
        <label>Відвідувань<input type="text" inputMode="numeric" pattern="[0-9]*" placeholder="8" value={planLessons} onChange={(event) => onPlanLessonsChange(digitsOnly(event.target.value))} /><small className="fieldHint">Можна залишити порожнім для необмежених відвідувань у межах днів.</small></label>
        <div className="formNotice tariffRuleNotice">Потрібно заповнити хоча б одне: <b>дні</b> або <b>відвідування</b>. Якщо заповнені обидва — період завершується за правилом, що настане раніше.</div>
        {planEditId && <label className="toggleRow"><input type="checkbox" checked={planActive} onChange={(event) => onPlanActiveChange(event.target.checked)} /><span><b>Активний тариф</b><small>Неактивний тариф не можна призначити новому учню, але чинні абонементи залишаються в історії та довикористовуються.</small></span></label>}
        <button className="primary full" disabled={planSaving || !planName.trim() || planPrice === "" || (!planDays && !planLessons)} onClick={() => void onSavePlan()}>{planSaving ? "Зберігаємо…" : planEditId ? "Зберегти зміни" : "Створити тариф"}</button>
        {planEditId && <div className="tariffHistoryWrap">
          <button className="subtleHistoryAction" type="button" disabled={planHistoryLoading} onClick={() => void onTogglePlanHistory()}>{planHistoryLoading ? "Завантажуємо…" : planHistoryOpen ? "Сховати історію змін" : "Історія змін тарифу"}</button>
          {planHistoryOpen && <div className="tariffHistoryList">
            {planHistory.length === 0 && <small>Змін цього тарифу ще не було.</small>}
            {planHistory.map((event) => <div key={event.id}><span>{new Date(event.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })}</span><b>{event.event_type === "subscription_plan.created" ? "Створено" : "Змінено"}</b><small>{tariffHistoryDetail(event)}</small></div>)}
          </div>}
        </div>}
      </div>
    </div>}

    {showPaymentForm && <div className="modalBackdrop" data-testid="payment-create-dialog">
      <div className="groupModal" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" onClick={onClosePaymentForm}>×</button>
        <p className="eyebrow">Нарахування</p><h2>Створити оплату</h2>
        <label>Учень<select value={paymentStudentId} onChange={(event) => onPaymentStudentChange(event.target.value)}>{activeStudents.map((student) => <option value={student.id} key={student.id}>{student.child} · відповідальний: {student.parent}</option>)}</select></label>
        <label>Абонемент<select value={paymentPlanId} onChange={(event) => onPaymentPlanChange(event.target.value)}>{pricedActivePlans.map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {money(plan.price)}</option>)}</select></label>
        <label>Оплатити до<input type="date" value={paymentDueDate} min={paymentMinDate} onChange={(event) => onPaymentDueDateChange(event.target.value)} /></label>
        <label className="toggleRow"><input type="checkbox" checked={paymentAutoRenew} onChange={(event) => onPaymentAutoRenewChange(event.target.checked)} /><span><b>Автопродовження</b><small>Наступне нарахування створиться автоматично перед завершенням цього періоду.</small></span></label>
        {activeStudents.length === 0 && <div className="formNotice">Спочатку зарахуйте хоча б одного учня.</div>}
        {pricedActivePlans.length === 0 && <div className="formNotice">Створіть або активуйте тариф із ціною, щоб зробити нарахування.</div>}
        <button className="primary full" disabled={paymentSaving || !paymentStudentId || !paymentPlanId || !plans.some((plan) => plan.id === paymentPlanId && plan.isActive && plan.price > 0)} onClick={() => void onCreatePayment()}>{paymentSaving ? "Створюємо…" : "Створити нарахування"}</button>
      </div>
    </div>}

    {paymentActionId && paymentActionType && <div className="modalBackdrop" data-testid="payment-action-dialog">
      <div className="groupModal" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" onClick={onClosePaymentAction}>×</button>
        <p className="eyebrow">Фінансова операція</p>
        <h2>{paymentActionType === "partial" ? "Часткова оплата" : paymentActionType === "refund" ? "Повернення коштів" : "Коригування нарахування"}</h2>
        <label>Сума<input type="text" inputMode="decimal" value={paymentActionAmount} onChange={(event) => onPaymentActionAmountChange(event.target.value.replace(/[^0-9.,]/g, "").replace(",", "."))} placeholder="0" /></label>
        {paymentActionType === "partial" && <label>Спосіб<select value={paymentActionMethod} onChange={(event) => onPaymentActionMethodChange(event.target.value as PaymentMethod)}><option value="card">Картка</option><option value="cash">Готівка</option><option value="bank">Переказ</option></select></label>}
        {paymentActionType === "adjustment" && <label>Тип коригування<select value={paymentAdjustmentDirection} onChange={(event) => onPaymentAdjustmentDirectionChange(event.target.value as AdjustmentDirection)}><option value="decrease">Зменшити нарахування</option><option value="increase">Збільшити нарахування</option></select></label>}
        <label>{paymentActionType === "refund" ? "Причина повернення" : paymentActionType === "adjustment" ? "Причина коригування" : "Коментар"}<textarea value={paymentActionReason} onChange={(event) => onPaymentActionReasonChange(event.target.value)} placeholder={paymentActionType === "refund" ? "Наприклад: перерахунок за невикористані заняття" : "Необов’язково"} /></label>
        {paymentActionType === "refund" && <div className="formNotice">Повернення одночасно зменшує суму нарахування на цю ж величину, тому після коректного повернення новий борг автоматично не виникає.</div>}
        <button className="primary full" disabled={paymentActionSaving || !paymentActionAmount} onClick={() => void onSubmitPaymentAction()}>{paymentActionSaving ? "Зберігаємо…" : "Підтвердити"}</button>
      </div>
    </div>}

    {planChangeSubscriptionId && <div className="modalBackdrop" data-testid="plan-change-dialog">
      <div className="groupModal tariffChangeModal" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" onClick={onClosePlanChange}>×</button>
        <p className="eyebrow">Абонемент</p><h2>Змінити тариф зараз</h2>
        {!planChangeResult ? <>
          <div className="formNotice">Вже використані заняття залишаться за старою ціною. Лише невикористані заняття поточного періоду перерахуються за новою ціною. Різниця стане кредитом або боргом.</div>
          <label>Новий тариф<select value={planChangePlanId} onChange={(event) => onPlanChangePlanIdChange(event.target.value)}>{plans.filter((plan) => plan.isActive && plan.id !== subscriptions.find((item) => item.id === planChangeSubscriptionId)?.plan_id).map((plan) => <option value={plan.id} key={plan.id}>{plan.name} · {money(plan.price)} · {[plan.days ? plan.days + " днів" : "", plan.lessons ? plan.lessons + " відв." : ""].filter(Boolean).join(" / ")}</option>)}</select></label>
          <label>Причина зміни<textarea value={planChangeReason} onChange={(event) => onPlanChangeReasonChange(event.target.value)} maxLength={300} placeholder="Коротко: чому тариф змінюється з поточного періоду" /></label>
          <button className="primary full" disabled={planChangeSaving || !planChangePlanId || !planChangeReason.trim()} onClick={() => void onSubmitPlanChange()}>{planChangeSaving ? "Перераховуємо…" : "Змінити і перерахувати"}</button>
        </> : <div className="tariffChangeSuccess"><b>✓ Перераховано</b><p>{planChangeResult}</p><button className="primary full" onClick={onClosePlanChange}>Закрити</button></div>}
      </div>
    </div>}

    {pauseSubscriptionId && <div className="modalBackdrop" data-testid="subscription-pause-dialog">
      <div className="groupModal" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" onClick={onClosePause}>×</button>
        <p className="eyebrow">Абонемент</p><h2>Поставити на паузу</h2>
        <label>Пауза з<input type="date" value={pauseStart} onChange={(event) => onPauseStartChange(event.target.value)} /></label>
        <label>Відновити з<input type="date" value={pauseResumeOn} min={pauseStart} onChange={(event) => onPauseResumeOnChange(event.target.value)} /><small className="fieldHint">Можна залишити порожнім і відновити вручну пізніше.</small></label>
        <label>Причина<textarea value={pauseNote} onChange={(event) => onPauseNoteChange(event.target.value)} placeholder="Канікули, хвороба, поїздка…" /></label>
        <div className="formNotice">Після відновлення кінець абонемента автоматично посунеться на фактичну кількість днів паузи.</div>
        <button className="primary full" onClick={() => void onSubmitPause()}>Поставити на паузу</button>
      </div>
    </div>}
  </>;
}
