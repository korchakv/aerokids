import type { ApiStudentSubscription } from "../../api";
import type { PaymentDemo, PlanDemo } from "../billing/model";
import type { GroupItem } from "../groups/types";
import { leadActionMeta, type EntityId, type Lead } from "../leads/model";
import type { LessonItem } from "../teaching/model";
import { formatUaPhone } from "../../utils/contact";
import { localDateInput } from "../../utils/date";

type DashboardViewProps = {
  groups: GroupItem[];
  leads: Lead[];
  plans: PlanDemo[];
  todayLessons: LessonItem[];
  todayTrials: Lead[];
  dashboardLeadTasks: Lead[];
  renewalSubscriptionTasks: ApiStudentSubscription[];
  dashboardPaymentTasks: PaymentDemo[];
  dashboardTaskCount: number;
  todayKey: string;
  canSeeSchedule: boolean;
  money: (value: number) => string;
  onOpenSchedule: () => void;
  onOpenLesson: (lessonId: EntityId) => void;
  onOpenGroup: (groupId: EntityId) => void;
  onOpenLead: (leadId: EntityId) => void;
  onOpenStudent: (studentId: EntityId) => void;
  onOpenPayment: (paymentId: EntityId) => void;
};

export function DashboardView({
  groups,
  leads,
  plans,
  todayLessons,
  todayTrials,
  dashboardLeadTasks,
  renewalSubscriptionTasks,
  dashboardPaymentTasks,
  dashboardTaskCount,
  todayKey,
  canSeeSchedule,
  money,
  onOpenSchedule,
  onOpenLesson,
  onOpenGroup,
  onOpenLead,
  onOpenStudent,
  onOpenPayment,
}: DashboardViewProps) {
  return <section className="todayDashboard">
    <div className="todayIntro">
      <div>
        <p className="eyebrow">Сьогодні · {new Date().toLocaleDateString("uk-UA", { weekday: "long", day: "numeric", month: "long" })}</p>
        <h2>{dashboardTaskCount > 0 ? "Що потребує уваги" : "Усе важливе на сьогодні під контролем"}</h2>
      </div>
      {dashboardTaskCount > 0 && <span className="todayTaskCount">{dashboardTaskCount} {dashboardTaskCount === 1 ? "дія" : dashboardTaskCount < 5 ? "дії" : "дій"}</span>}
    </div>

    {canSeeSchedule && <article className="panel todayLessonsPanel">
      <div className="todaySectionHead">
        <div><p className="eyebrow">Розклад</p><h2>Заняття сьогодні</h2></div>
        <button className="link" onClick={onOpenSchedule}>Розклад →</button>
      </div>
      <div className="todayLessonList">
        {todayLessons.map((lesson) => {
          const group = groups.find((item) => item.id === lesson.groupId);
          return <div className="todayLessonRow" key={lesson.id}>
            <button className="todayLessonMain" onClick={() => onOpenLesson(lesson.id)}>
              <time>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
              <span><b>{group?.name ?? "Заняття"}</b><small>{lesson.topic || "Тема не вказана"} · {lesson.duration} хв{group?.location ? " · " + group.location : ""}</small></span>
              <em>Журнал →</em>
            </button>
            {group && <button className="todayGroupLink" onClick={() => onOpenGroup(group.id)}>Група</button>}
          </div>;
        })}
        {todayTrials.map((lead) => <button className="todayLessonRow todayTrialRow" key={"trial-" + lead.id} onClick={() => onOpenLead(lead.id)}>
          <span className="todayLessonMain">
            <time>{new Date(lead.trialAt!).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
            <span><b>{lead.child} · пробне</b><small>{lead.parent}{lead.trialLocation ? " · " + lead.trialLocation : ""}</small></span>
            <em>Заявка →</em>
          </span>
        </button>)}
        {todayLessons.length === 0 && todayTrials.length === 0 && <div className="todayEmpty">На сьогодні занять не заплановано.</div>}
      </div>
    </article>}

    <article className="panel todayActionsPanel">
      <div className="todaySectionHead">
        <div><p className="eyebrow">Дії</p><h2>Потрібно зробити сьогодні</h2></div>
      </div>
      <div className="todayActionList">
        {dashboardLeadTasks.map((lead) => {
          const kind = lead.status === "Нова"
            ? "Нова заявка"
            : lead.status === "Після пробного"
              ? "Після пробного"
              : lead.trialResult === "no_show"
                ? "Не прийшов на пробне"
                : lead.trialResult === "cancelled"
                  ? "Пробне скасовано"
                  : "Зв’язатися";
          const detail = lead.nextContactAt && localDateInput(new Date(lead.nextContactAt)) <= todayKey
            ? "Контакт запланований " + new Date(lead.nextContactAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
            : lead.parent + " · " + formatUaPhone(lead.phone);
          const meta = leadActionMeta(lead);
          return <button className="todayActionRow" key={"lead-" + lead.id} onClick={() => onOpenLead(lead.id)}>
            <span className={"todayActionType lead action-" + meta.type}>{meta.icon} {meta.label}</span>
            <span className="todayActionText"><b>{lead.child}, {lead.age} років</b><small>{kind} · {detail}</small></span>
            <span className="todayActionArrow">→</span>
          </button>;
        })}
        {renewalSubscriptionTasks.map((subscription) => {
          const student = leads.find((lead) => lead.id === subscription.student_id);
          const plan = plans.find((item) => item.id === subscription.plan_id);
          return <button className="todayActionRow" key={"renewal-" + subscription.id} onClick={() => onOpenStudent(subscription.student_id)}>
            <span className="todayActionType payment">Абонемент</span>
            <span className="todayActionText"><b>{student?.child ?? "Учень"} · залишилось 1 заняття</b><small>{plan?.name ?? "Абонемент"} · скоро продовження</small></span>
            <span className="todayActionArrow">→</span>
          </button>;
        })}
        {dashboardPaymentTasks.map((payment) => {
          const student = leads.find((lead) => lead.id === payment.studentId);
          const isOverdue = payment.dueDate < todayKey || payment.status === "overdue";
          return <button className="todayActionRow" key={"payment-" + payment.id} onClick={() => onOpenPayment(payment.id)}>
            <span className={"todayActionType payment " + (isOverdue ? "urgent" : "")}>{isOverdue ? "Борг" : "Оплата"}</span>
            <span className="todayActionText"><b>{student?.child ?? "Учень"} · {money(payment.balanceAmount)}</b><small>{isOverdue ? "Прострочено" : "Оплатити сьогодні"} · термін {new Date(payment.dueDate + "T00:00:00").toLocaleDateString("uk-UA")}</small></span>
            <span className="todayActionArrow">→</span>
          </button>;
        })}
        {dashboardTaskCount === 0 && <div className="todayEmpty done">На сьогодні немає невиконаних важливих дій.</div>}
      </div>
    </article>
  </section>;
}
