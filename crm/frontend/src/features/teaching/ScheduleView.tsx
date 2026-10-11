import { useState } from "react";
import { DateTimeEditor, DurationSelect, ScheduleSlotEditor, type DraftScheduleSlot } from "../../components/ScheduleEditors";
import type { EntityId, Lead } from "../leads/model";
import type { GroupItem } from "../groups/types";
import type { LessonItem } from "../teaching/model";
import { dateValue, localDateInput } from "../../utils/date";

type ScheduleViewProps = {
  groups: GroupItem[];
  lessonsThisWeek: LessonItem[];
  trialsThisWeek: Lead[];
  scheduleWeekStart: Date;
  scheduleWeekEnd: Date;
  scheduleWeekDays: Date[];
  completedThisWeek: number;
  unfinishedPastThisWeek: number;
  scheduleFilterGroupId: EntityId | "all";
  scheduleWeekOffset: number;
  todayKey: string;
  attendance: Record<EntityId, Record<EntityId, unknown>>;
  groupTeacherName: (groupId: EntityId) => string | undefined;
  onScheduleFilterChange: (groupId: EntityId | "all") => void;
  onPreviousWeek: () => void;
  onCurrentWeek: () => void;
  onNextWeek: () => void;
  onOpenLead: (leadId: EntityId) => void;
  onOpenLesson: (lessonId: EntityId) => void;

  newLessonGroupId: EntityId;
  newLessonAt: string;
  newLessonDuration: number;
  newLessonTopic: string;
  onNewLessonGroupChange: (groupId: EntityId) => void;
  onNewLessonAtChange: (value: string) => void;
  onNewLessonDurationChange: (value: number) => void;
  onNewLessonTopicChange: (value: string) => void;
  onCreateLesson: () => void;

  canManageRecurringSchedule: boolean;
  scheduleGroupId: EntityId;
  scheduleWeekday: number;
  scheduleTime: string;
  scheduleDuration: number;
  onScheduleGroupChange: (groupId: EntityId) => void;
  onCreateGroupSchedule: (slots: DraftScheduleSlot[]) => Promise<boolean>;
};

export function ScheduleView({
  groups,
  lessonsThisWeek,
  trialsThisWeek,
  scheduleWeekStart,
  scheduleWeekEnd,
  scheduleWeekDays,
  completedThisWeek,
  unfinishedPastThisWeek,
  scheduleFilterGroupId,
  scheduleWeekOffset,
  todayKey,
  attendance,
  groupTeacherName,
  onScheduleFilterChange,
  onPreviousWeek,
  onCurrentWeek,
  onNextWeek,
  onOpenLead,
  onOpenLesson,
  newLessonGroupId,
  newLessonAt,
  newLessonDuration,
  newLessonTopic,
  onNewLessonGroupChange,
  onNewLessonAtChange,
  onNewLessonDurationChange,
  onNewLessonTopicChange,
  onCreateLesson,
  canManageRecurringSchedule,
  scheduleGroupId,
  scheduleWeekday,
  scheduleTime,
  scheduleDuration,
  onScheduleGroupChange,
  onCreateGroupSchedule,
}: ScheduleViewProps) {
  const [scheduleCreateOpen, setScheduleCreateOpen] = useState(false);
  const [scheduleCreateMode, setScheduleCreateMode] = useState<"lesson" | "recurring">("lesson");
  const [scheduleSlots, setScheduleSlots] = useState<DraftScheduleSlot[]>([{ weekday: scheduleWeekday, start_time: scheduleTime, duration_minutes: scheduleDuration }]);

  const submitScheduleCreation = async () => {
    if (scheduleCreateMode === "lesson") {
      await onCreateLesson();
      setScheduleCreateOpen(false);
      return;
    }
    if (await onCreateGroupSchedule(scheduleSlots)) setScheduleCreateOpen(false);
  };

  return <section className="scheduleWorkspace" data-testid="schedule-workspace">
    <article className="panel schedulePanel scheduleCalendar">
      <div className="scheduleToolbar scheduleToolbarClear">
        <div>
          <p className="eyebrow">Календар</p>
          <h2>{scheduleWeekStart.toLocaleDateString("uk-UA", { day: "numeric", month: "long" })} — {scheduleWeekEnd.toLocaleDateString("uk-UA", { day: "numeric", month: "long", year: "numeric" })}</h2>
          <div className="scheduleWeekSummary">
            <span><b>{lessonsThisWeek.length}</b> занять</span>
            <span className="done"><b>{completedThisWeek}</b> проведено</span>
            {unfinishedPastThisWeek > 0 && <span className="attention"><b>{unfinishedPastThisWeek}</b> не завершено</span>}
            {trialsThisWeek.length > 0 && <span className="trial"><b>{trialsThisWeek.length}</b> пробних</span>}
          </div>
        </div>
        <div className="scheduleToolbarActions">
          <label className="scheduleGroupFilter">Показати<select value={scheduleFilterGroupId} onChange={(event) => onScheduleFilterChange(event.target.value)}>
            <option value="all">Усі групи + пробні</option>
            {groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}
          </select></label>
          <button type="button" className="primary scheduleCreateTrigger" onClick={() => setScheduleCreateOpen(true)}>Додати заняття / розклад</button>
          <div className="scheduleNav">
            <button className="search" aria-label="Попередній тиждень" onClick={onPreviousWeek}>←</button>
            <button className="search" onClick={onCurrentWeek} disabled={scheduleWeekOffset === 0}>Цей тиждень</button>
            <button className="search" aria-label="Наступний тиждень" onClick={onNextWeek}>→</button>
          </div>
        </div>
      </div>
      <div className="scheduleLegend">
        <span className="planned"><i></i>Заплановано</span>
        <span className="completed"><i></i>Проведено</span>
        <span className="missed"><i></i>Не проведено</span>
        {scheduleFilterGroupId === "all" && <span className="trial"><i></i>Пробне</span>}
      </div>
      <div className="mobileScheduleAgenda">
        {scheduleWeekDays.map((date) => {
          const dayKey = localDateInput(date);
          const dayLessons = lessonsThisWeek.filter((lesson) => localDateInput(new Date(lesson.startsAt)) === dayKey);
          const dayTrials = trialsThisWeek.filter((lead) => lead.trialAt && localDateInput(new Date(lead.trialAt)) === dayKey);
          const items = [
            ...dayLessons.map((lesson) => ({ kind: "lesson" as const, at: lesson.startsAt, lesson })),
            ...dayTrials.map((lead) => ({ kind: "trial" as const, at: lead.trialAt!, lead })),
          ].sort((a, b) => dateValue(a.at) - dateValue(b.at));
          if (items.length === 0) return null;
          const isToday = dayKey === todayKey;
          return <section className={"mobileScheduleDay " + (isToday ? "today" : "")} key={"mobile-" + dayKey}>
            <div className="mobileScheduleDayHead"><b>{date.toLocaleDateString("uk-UA", { weekday: "short", day: "2-digit", month: "2-digit" })}</b>{isToday && <span>Сьогодні</span>}</div>
            <div className="mobileScheduleRows">
              {items.map((item) => {
                if (item.kind === "trial") {
                  return <button className="mobileScheduleRow trial" key={"mtrial-" + item.lead.id} onClick={() => onOpenLead(item.lead.id)}>
                    <time>{new Date(item.at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
                    <span><b>{item.lead.child}</b><small>Пробне</small></span>
                    <i>›</i>
                  </button>;
                }
                const group = groups.find((candidate) => candidate.id === item.lesson.groupId);
                const isPast = dateValue(item.lesson.startsAt) < Date.now();
                const state = item.lesson.status === "completed" ? "completed" : isPast ? "missed" : "planned";
                const label = state === "completed" ? "Проведено" : state === "missed" ? "Не проведено" : "Заплановано";
                return <button className={"mobileScheduleRow " + state} key={"mlesson-" + item.lesson.id} onClick={() => onOpenLesson(item.lesson.id)}>
                  <time>{new Date(item.at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time>
                  <span><b>{group?.name ?? "Група"}</b><small>{label}</small></span>
                  <i>›</i>
                </button>;
              })}
            </div>
          </section>;
        })}
        {lessonsThisWeek.length === 0 && trialsThisWeek.length === 0 && <div className="mobileScheduleEmpty">На цей тиждень подій немає.</div>}
      </div>
      <div className="weekGrid weekGridConcrete scheduleWeekClear">
        {scheduleWeekDays.map((date) => {
          const dayKey = localDateInput(date);
          const dayLessons = lessonsThisWeek.filter((lesson) => localDateInput(new Date(lesson.startsAt)) === dayKey);
          const dayTrials = trialsThisWeek.filter((lead) => lead.trialAt && localDateInput(new Date(lead.trialAt)) === dayKey);
          const isToday = dayKey === todayKey;
          return <div className={"dayColumn scheduleDay " + (isToday ? "today" : "")} key={dayKey}>
            <div className="scheduleDayHead">
              <div><b>{date.toLocaleDateString("uk-UA", { weekday: "long" })}</b>{isToday && <em>Сьогодні</em>}</div>
              <span>{date.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" })}</span>
            </div>
            <div className="scheduleDayLessons">
              {[...dayLessons].sort((a, b) => dateValue(a.startsAt) - dateValue(b.startsAt)).map((lesson) => {
                const group = groups.find((item) => item.id === lesson.groupId);
                const teacher = group ? (group.teacherName ?? groupTeacherName(group.id)) : undefined;
                const marked = lesson.attendanceTotal ?? Object.keys(attendance[lesson.id] ?? {}).length;
                const total = group?.members.length ?? 0;
                const isPast = dateValue(lesson.startsAt) < Date.now();
                const state = lesson.status === "completed" ? "completed" : isPast ? "missed" : "planned";
                const statusText = state === "completed" ? "Проведено" : state === "missed" ? "Не проведено" : "Заплановано";
                return <button className={"scheduleCard concreteLessonCard " + state} key={lesson.id} onClick={() => onOpenLesson(lesson.id)}>
                  <div className="scheduleCardTop"><time>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time><span className={"scheduleStatus " + state}>{statusText}</span></div>
                  <strong>{group?.name ?? "Група"}</strong>
                  <small>{lesson.topic || "Тема ще не вказана"}</small>
                  <div className="scheduleCardMeta">{teacher && <span>{teacher}</span>}{total > 0 && <span>{marked}/{total} відмічено</span>}</div>
                </button>;
              })}
              {dayTrials.map((lead) => <button className="scheduleCard trialCalendarCard" key={"trial-" + lead.id} onClick={() => onOpenLead(lead.id)}>
                <div className="scheduleCardTop"><time>{new Date(lead.trialAt!).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</time><span className="scheduleStatus trial">Пробне</span></div>
                <strong>{lead.child}</strong>
                <small>{lead.age} років{lead.trialLocation ? " · " + lead.trialLocation : ""}</small>
                <div className="scheduleCardMeta"><span>Відкрити заявку →</span></div>
              </button>)}
              {dayLessons.length === 0 && dayTrials.length === 0 && <div className="scheduleDayEmpty">Вільний день</div>}
            </div>
          </div>;
        })}
      </div>
    </article>

    {scheduleCreateOpen && <div className="modalBackdrop">
      <div className="groupModal scheduleCreateModal" role="dialog" aria-modal="true" aria-labelledby="schedule-create-title">
        <div className="workflowHead">
          <div><p className="eyebrow">Календар</p><h2 id="schedule-create-title">Додати заняття або розклад</h2></div>
          <button type="button" aria-label="Закрити" onClick={() => setScheduleCreateOpen(false)}>×</button>
        </div>
        <label>Тип створення<select value={scheduleCreateMode} onChange={(event) => setScheduleCreateMode(event.target.value as "lesson" | "recurring")}>
          <option value="lesson">Разове заняття</option>
          {canManageRecurringSchedule && <option value="recurring">Постійний розклад групи</option>}
        </select></label>
        <label>Група<select value={scheduleCreateMode === "lesson" ? newLessonGroupId : scheduleGroupId} onChange={(event) => {
          if (scheduleCreateMode === "lesson") onNewLessonGroupChange(event.target.value);
          else onScheduleGroupChange(event.target.value);
        }}>
          <option value="">Оберіть групу</option>
          {groups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}
        </select></label>
        {scheduleCreateMode === "lesson" ? <>
          <DateTimeEditor label="Дата і час" value={newLessonAt} onChange={onNewLessonAtChange} />
          <DurationSelect value={newLessonDuration} onChange={onNewLessonDurationChange} />
          <label>Тема<input value={newLessonTopic} onChange={(event) => onNewLessonTopicChange(event.target.value)} placeholder="Можна заповнити пізніше в журналі" /></label>
        </> : <>
          <ScheduleSlotEditor value={scheduleSlots} onChange={setScheduleSlots} />
        </>}
        {groups.length === 0 && <div className="emptyState compactEmpty">Спочатку створіть групу, щоб додати заняття або розклад.</div>}
        <button type="button" className="primary full" disabled={groups.length === 0 || (scheduleCreateMode === "lesson" ? !newLessonGroupId : !scheduleGroupId || scheduleSlots.length === 0)} onClick={() => { void submitScheduleCreation(); }}>
          {scheduleCreateMode === "lesson" ? "Створити заняття" : "Додати регулярний розклад"}
        </button>
      </div>
    </div>}

  </section>;
}
