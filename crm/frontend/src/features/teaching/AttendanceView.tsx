import { UiIcon } from "../../components/UiIcon";
import type { ApiStudentAttendanceHistoryItem } from "../../api";
import type { EntityId, Lead } from "../leads/model";
import type { GroupItem } from "../groups/types";
import type { LessonItem } from "./model";
import { attendanceStatusLabel, type AttendanceValue } from "./attendance";
import { dateValue, weekdayLong } from "../../utils/date";

type AttendanceCounts = {
  present: number;
  absent: number;
  late: number;
  excused: number;
  total: number;
};

type AttendanceViewProps = {
  attendanceDayOffset: number;
  attendanceDay: Date;
  attendanceDayKey: string;
  attendanceTodayKey: string;
  attendanceNow: number;
  journalLessons: LessonItem[];
  groups: GroupItem[];
  nearestAttendanceLesson?: LessonItem;
  selectedLessonId: EntityId | null;
  completedAttendanceLessons: LessonItem[];
  pendingAttendanceLessons: LessonItem[];
  lessonSaveNotice: string;
  focusedAttendanceStudentId: EntityId | null;
  focusedAttendanceStudent?: Lead;
  focusedAttendanceGroup?: GroupItem;
  focusedAttendanceRate: number;
  focusedAttendanceCounts: AttendanceCounts;
  studentAttendanceHistoryLoading: boolean;
  focusedAttendanceRows: ApiStudentAttendanceHistoryItem[];
  selectedLesson?: LessonItem;
  lessonGroup?: GroupItem;
  lessonEditing: boolean;
  lessonTopicDraft: string;
  lessonNotesDraft: string;
  lessonDetailsSaving: boolean;
  lessonStudents: Lead[];
  attendance: Record<EntityId, Record<EntityId, AttendanceValue>>;
  attendanceNotes: Record<EntityId, Record<EntityId, string>>;
  attendanceLoading: boolean;
  attendanceSaving: boolean;
  onPreviousDay: () => void;
  onToday: () => void;
  onNextDay: () => void;
  onSelectLesson: (lessonId: EntityId) => void;
  onCloseStudentHistory: () => void;
  onOpenLesson: (lessonId: EntityId) => void;
  onBackToSchedule: () => void;
  onEditLesson: () => void;
  onCancelLessonEdit: () => void;
  onMarkAllPresent: () => void;
  onMarkUnmarkedAbsent: () => void;
  onLessonTopicChange: (value: string) => void;
  onLessonNotesChange: (value: string) => void;
  onSaveLessonDetails: () => void;
  onMarkAttendance: (studentId: EntityId, value: AttendanceValue) => void;
  onAttendanceNoteChange: (studentId: EntityId, value: string) => void;
  onSaveAttendance: () => void;
};

export function AttendanceView({
  attendanceDayOffset,
  attendanceDay,
  attendanceDayKey,
  attendanceTodayKey,
  attendanceNow,
  journalLessons,
  groups,
  nearestAttendanceLesson,
  selectedLessonId,
  completedAttendanceLessons,
  pendingAttendanceLessons,
  lessonSaveNotice,
  focusedAttendanceStudentId,
  focusedAttendanceStudent,
  focusedAttendanceGroup,
  focusedAttendanceRate,
  focusedAttendanceCounts,
  studentAttendanceHistoryLoading,
  focusedAttendanceRows,
  selectedLesson,
  lessonGroup,
  lessonEditing,
  lessonTopicDraft,
  lessonNotesDraft,
  lessonDetailsSaving,
  lessonStudents,
  attendance,
  attendanceNotes,
  attendanceLoading,
  attendanceSaving,
  onPreviousDay,
  onToday,
  onNextDay,
  onSelectLesson,
  onCloseStudentHistory,
  onOpenLesson,
  onBackToSchedule,
  onEditLesson,
  onCancelLessonEdit,
  onMarkAllPresent,
  onMarkUnmarkedAbsent,
  onLessonTopicChange,
  onLessonNotesChange,
  onSaveLessonDetails,
  onMarkAttendance,
  onAttendanceNoteChange,
  onSaveAttendance,
}: AttendanceViewProps) {
  return <section className="attendanceLayout" data-testid="attendance-workspace">
    <article className="panel lessonListPanel">
      <div className="attendanceWeekHead attendanceDayHead">
        <div>
          <p className="eyebrow">{attendanceDayOffset === 0 ? "Сьогодні" : "Журнал за день"}</p>
          <h2>{attendanceDay.toLocaleDateString("uk-UA", { weekday: "long", day: "numeric", month: "long" })}</h2>
        </div>
        <span className="counter">{journalLessons.length}</span>
      </div>
      <div className="attendanceWeekNav attendanceDayNav">
        <button className="search" aria-label="Попередній день" title="Попередній день" onClick={onPreviousDay}>←</button>
        <button className="search" disabled={attendanceDayOffset === 0} onClick={onToday}>Сьогодні</button>
        <button className="search" aria-label="Наступний день" title="Наступний день" onClick={onNextDay}>→</button>
      </div>
      <div className="lessonList attendanceDailyList">
        {journalLessons.map((lesson) => {
          const group = groups.find((candidate) => candidate.id === lesson.groupId);
          const start = dateValue(lesson.startsAt);
          const end = start + lesson.duration * 60_000;
          const completed = lesson.status === "completed";
          const inProgress = !completed && attendanceDayKey === attendanceTodayKey && start <= attendanceNow && attendanceNow <= end;
          const overdue = !completed && end < attendanceNow;
          const nearest = !completed && lesson.id === nearestAttendanceLesson?.id;
          const rowState = completed ? "completed" : inProgress ? "current" : overdue ? "missed" : nearest ? "nearest" : "planned";
          const endTime = new Date(end).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
          const summary = completed
            ? `Відмічено · ${lesson.attendancePresent ?? 0} є · ${lesson.attendanceAbsent ?? 0} нема`
            : inProgress
              ? `Зараз · до ${endTime}`
              : overdue
                ? "Потрібно відмітити відвідування"
                : nearest
                  ? "Найближче заняття"
                  : "Заплановано";
          return <button className={"lessonRow attendanceDailyRow " + rowState + " " + (lesson.id === selectedLessonId ? "active" : "")} key={lesson.id} onClick={() => onSelectLesson(lesson.id)}>
            <time>
              <strong>{new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</strong>
              <small>до {endTime}</small>
            </time>
            <span><b>{group?.name ?? "Група"}</b><small>{summary}</small></span>
            <i className={"lessonStateBadge " + rowState}>{completed ? "✓ Відмічено" : inProgress ? "Зараз" : overdue ? "! Відмітити" : nearest ? "Найближче" : "Заплановано"}</i>
          </button>;
        })}
        {journalLessons.length === 0 && <div className="emptyState compactEmpty">На цей день занять немає.</div>}
      </div>
      {completedAttendanceLessons.length > 0 && pendingAttendanceLessons.length > 0 && <div className="attendanceCompletedHint">Відмічені заняття автоматично переходять униз списку.</div>}
    </article>

    <article className="panel attendancePanel">
      {lessonSaveNotice && <div className="lessonSaveNotice">✓ Збережено</div>}
      {focusedAttendanceStudentId ? <div className="studentAttendanceOverview">
        <div className="studentAttendanceHero">
          <button className="lessonBackButton" onClick={onCloseStudentHistory}><UiIcon name="back" size={16} /><span>До журналу занять</span></button>
          <div className="studentAttendanceTitle">
            <span>{focusedAttendanceStudent?.child?.[0] ?? "?"}</span>
            <div><p className="eyebrow">Відвідування учня</p><h2>{focusedAttendanceStudent?.child ?? "Учень"}</h2><small>{focusedAttendanceGroup?.name ?? "Усі групи"}{focusedAttendanceStudent?.parent ? " · " + focusedAttendanceStudent.parent : ""}</small></div>
          </div>
        </div>
        <div className="studentAttendanceStats">
          <article><small>Відвідуваність</small><strong>{focusedAttendanceRate}%</strong><span>{focusedAttendanceCounts.total} занять</span></article>
          <article><small>Був</small><strong>{focusedAttendanceCounts.present}</strong><span>занять</span></article>
          <article><small>Запізнився</small><strong>{focusedAttendanceCounts.late}</strong><span>занять</span></article>
          <article><small>Пропуски</small><strong>{focusedAttendanceCounts.absent + focusedAttendanceCounts.excused}</strong><span>{focusedAttendanceCounts.excused} поважних</span></article>
        </div>
        <div className="studentAttendanceHistory">
          <div className="studentAttendanceHistoryHead"><span>Дата</span><span>Заняття</span><span>Статус</span><span>Коментар</span><span></span></div>
          {studentAttendanceHistoryLoading && <div className="emptyState compactEmpty">Завантажуємо історію…</div>}
          {!studentAttendanceHistoryLoading && focusedAttendanceRows.length === 0 && <div className="emptyState">У цього учня ще немає відмічених занять у цій групі.</div>}
          {focusedAttendanceRows.map((row) => <div className="studentAttendanceHistoryRow" key={row.session_id}>
            <time><b>{weekdayLong(row.starts_at)}</b><span>{new Date(row.starts_at).toLocaleDateString("uk-UA")}</span><small>{new Date(row.starts_at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></time>
            <span><b>{row.topic || "Заняття"}</b><small>{row.group_name} · {row.duration_minutes} хв</small></span>
            <span><b className={"protocolStatus " + row.status}>{attendanceStatusLabel(row.status)}</b></span>
            <span className="protocolNote">{row.note || "—"}</span>
            <button className="link" onClick={() => onOpenLesson(row.session_id)}>Заняття →</button>
          </div>)}
        </div>
      </div> : selectedLesson && <>
        <div className="lessonJournalHead">
          <button className="lessonBackButton" onClick={onBackToSchedule}><UiIcon name="back" size={16} /><span>До розкладу</span></button>
          <div className="panelHead">
            <div>
              <p className="eyebrow">{selectedLesson.status === "completed" ? "Проведене заняття" : "Конкретне заняття"}</p>
              <h2>{lessonGroup?.name}</h2>
              <p className="lessonMeta"><b>{weekdayLong(selectedLesson.startsAt)}</b> · {new Date(selectedLesson.startsAt).toLocaleDateString("uk-UA")} · {new Date(selectedLesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })} · {selectedLesson.duration} хв</p>
            </div>
            {selectedLesson.status === "completed" && !lessonEditing
              ? <button className="lessonEditButton" onClick={onEditLesson}>Редагувати</button>
              : <div className="attendanceQuickActions"><button className="search" onClick={onMarkAllPresent}>Усі присутні</button><button className="search" onClick={onMarkUnmarkedAbsent}>Непозначені → відсутні</button></div>}
          </div>
        </div>

        {lessonEditing ? <>
          <div className="lessonDetailsEditor">
            <label>Тема заняття<input value={lessonTopicDraft} onChange={(event) => onLessonTopicChange(event.target.value)} maxLength={240} placeholder="Що вивчаємо на занятті" /></label>
            <label>Домашнє завдання / примітки<textarea value={lessonNotesDraft} onChange={(event) => onLessonNotesChange(event.target.value)} maxLength={4000} placeholder="Наприклад: 3 кола в симуляторі без падіння. Або внутрішня примітка викладача." /></label>
            <div className="lessonDetailsActions"><small>Ці дані належать конкретному заняттю.</small><button className="search" disabled={lessonDetailsSaving} onClick={onSaveLessonDetails}>{lessonDetailsSaving ? "Зберігаємо…" : "Зберегти тему і завдання"}</button></div>
          </div>
          <div className="attendanceTable">
            {lessonStudents.map((student) => {
              const value = attendance[selectedLesson.id]?.[student.id];
              return <div id={"attendance-student-" + student.id} className={"attendanceRow " + (!value ? "unmarked " : "") + (focusedAttendanceStudentId === student.id ? "focusedStudent" : "")} key={student.id}>
                <span className="studentIdentity"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років{student.parent ? " · " + student.parent : ""}</small></b>{!value && <em className="unmarkedBadge">Не відмічено</em>}</span>
                <div className="attendanceButtons">
                  <button className={value === "present" ? "active present" : ""} onClick={() => onMarkAttendance(student.id, "present")}>✓ Є</button>
                  <button className={value === "absent" ? "active absent" : ""} onClick={() => onMarkAttendance(student.id, "absent")}>Нема</button>
                  <button className={value === "excused" ? "active excused" : ""} onClick={() => onMarkAttendance(student.id, "excused")}>Поважна причина</button>
                </div>
                {(value === "absent" || value === "excused") && <input className="attendanceReasonInput" value={attendanceNotes[selectedLesson.id]?.[student.id] ?? ""} onChange={(event) => onAttendanceNoteChange(student.id, event.target.value)} maxLength={300} placeholder={value === "excused" ? "Причина / коментар (за потреби)" : "Причина відсутності (за потреби)"} />}
              </div>;
            })}
            {lessonStudents.length === 0 && <div className="emptyState">У цій групі поки немає активних учнів. Додайте учнів до групи, щоб відмічати відвідування.</div>}
          </div>
          <div className="attendanceFooter">
            <span>{attendanceLoading ? "Завантажуємо…" : <>Позначено: <b>{Object.keys(attendance[selectedLesson.id] ?? {}).length}/{lessonStudents.length}</b>{lessonStudents.length > Object.keys(attendance[selectedLesson.id] ?? {}).length && <small> · ще {lessonStudents.length - Object.keys(attendance[selectedLesson.id] ?? {}).length}</small>}</>}</span>
            <div className="attendanceFooterActions">
              {selectedLesson.status === "completed" && <button className="search" onClick={onCancelLessonEdit}>Скасувати</button>}
              <button className="primary" disabled={attendanceSaving || attendanceLoading || lessonStudents.length === 0 || Object.keys(attendance[selectedLesson.id] ?? {}).length !== lessonStudents.length} onClick={onSaveAttendance}>{attendanceSaving ? "Зберігаємо…" : lessonStudents.length === 0 ? "Немає учнів для відмітки" : selectedLesson.status === "completed" ? "Зберегти зміни" : "Зберегти відвідування"}</button>
            </div>
          </div>
        </> : <div className="lessonProtocol">
          <section className="lessonProtocolSummary">
            <div><small>Тема заняття</small><strong>{selectedLesson.topic || "Не вказано"}</strong></div>
            <div><small>Домашнє завдання / примітки</small><strong>{selectedLesson.notes || "Немає"}</strong></div>
          </section>
          <div className="lessonProtocolTable">
            <div className="lessonProtocolRow lessonProtocolHead"><span>Учень</span><span>Статус</span><span>Причина / коментар</span></div>
            {lessonStudents.map((student) => {
              const value = attendance[selectedLesson.id]?.[student.id];
              const note = attendanceNotes[selectedLesson.id]?.[student.id]?.trim();
              return <div id={"attendance-student-" + student.id} className={"lessonProtocolRow " + (focusedAttendanceStudentId === student.id ? "focusedStudent" : "")} key={student.id}>
                <span className="protocolStudent"><i>{student.child[0]}</i><b>{student.child}<small>{student.age} років{student.parent ? " · " + student.parent : ""}</small></b></span>
                <span><b className={"protocolStatus " + (value ?? "unmarked")}>{attendanceStatusLabel(value)}</b></span>
                <span className="protocolNote">{note || "—"}</span>
              </div>;
            })}
          </div>
          <div className="lessonProtocolFooter">
            <span><b>{selectedLesson.attendancePresent ?? 0}</b> були</span>
            <span><b>{selectedLesson.attendanceLate ?? 0}</b> запізнились</span>
            <span><b>{selectedLesson.attendanceAbsent ?? 0}</b> не були</span>
            <span><b>{selectedLesson.attendanceExcused ?? 0}</b> поважна причина</span>
          </div>
        </div>}
      </>}
    </article>
  </section>;
}
