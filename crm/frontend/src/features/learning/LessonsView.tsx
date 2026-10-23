import { useEffect, useMemo, useState } from "react";
import type { Session } from "../../api";
import type { LessonItem } from "../teaching/model";
import {
  addMaterialLink, assignSessionLesson, loadCurriculum, loadGroupBaseline, loadStudentLearningProgress,
  materialFileUrl, removeCurriculumLesson, removeMaterial, saveCurriculumLesson,
  setGroupBaseline, updateStudentLearningProgress, uploadMaterial,
  type CurriculumLesson, type LearningProgress,
} from "../../api/learning";

type Props = {
  session: Session | null;
  groups: Array<{ id: string; name: string }>;
  students: Array<{ id: string; name: string; groupId: string | null }>;
  sessions: LessonItem[];
  canEdit: boolean;
};

const statusLabels: Record<LearningProgress["status"], string> = {
  completed: "Пройдено",
  missed: "Пропущено",
  before_join: "До вступу в групу",
  not_started: "Ще не проходили",
};

export function LessonsView({ session, groups, students, sessions, canEdit }: Props) {
  const [items, setItems] = useState<CurriculumLesson[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [outline, setOutline] = useState("");
  const [openLessonId, setOpenLessonId] = useState<string | null>(null);
  const [materialTitle, setMaterialTitle] = useState("");
  const [materialUrl, setMaterialUrl] = useState("");
  const [materialLessonId, setMaterialLessonId] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [baseline, setBaseline] = useState("0");
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [progress, setProgress] = useState<LearningProgress[]>([]);
  const [sessionFilter, setSessionFilter] = useState("all");

  async function refresh() {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      setItems(await loadCurriculum(session));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не вдалося завантажити програму.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [session?.organizationId]);

  useEffect(() => {
    if (!session || !selectedStudentId) { setProgress([]); return; }
    let cancelled = false;
    void loadStudentLearningProgress(selectedStudentId, session).then((rows) => {
      if (!cancelled) setProgress(rows);
    }).catch((caught: unknown) => {
      if (!cancelled) setError(caught instanceof Error ? caught.message : "Не вдалося завантажити прогрес.");
    });
    return () => { cancelled = true; };
  }, [session, selectedStudentId, items]);

  useEffect(() => {
    if (!session || !selectedGroupId) { setBaseline("0"); return; }
    void loadGroupBaseline(selectedGroupId, session).then((value) => setBaseline(String(value.completed_through)))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Не вдалося завантажити прогрес групи."));
  }, [session, selectedGroupId]);

  const studentsForGroup = useMemo(() => selectedGroupId
    ? students.filter((student) => student.groupId === selectedGroupId)
    : students, [students, selectedGroupId]);

  async function submitLesson(event: React.FormEvent) {
    event.preventDefault();
    if (!session || !title.trim()) return;
    setSaving(true);
    setError("");
    try {
      await saveCurriculumLesson(editingId, {
        title: title.trim(), outline: outline.trim() || undefined,
      }, session);
      setTitle(""); setOutline(""); setEditingId(null);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не вдалося зберегти урок.");
    } finally { setSaving(false); }
  }

  async function addLink(event: React.FormEvent) {
    event.preventDefault();
    if (!session || !materialLessonId || !materialTitle.trim() || !materialUrl.trim()) return;
    setSaving(true); setError("");
    try {
      await addMaterialLink(materialLessonId, { title: materialTitle.trim(), url: materialUrl.trim() }, session);
      setMaterialTitle(""); setMaterialUrl("");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не вдалося зберегти посилання.");
    } finally { setSaving(false); }
  }

  async function addFile(event: React.ChangeEvent<HTMLInputElement>, lessonId: string) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!session || !lessonId || !file) return;
    const form = new FormData(); form.append("title", materialLessonId === lessonId ? materialTitle.trim() || file.name : file.name); form.append("file", file);
    setSaving(true); setError("");
    try { await uploadMaterial(lessonId, form, session); setMaterialTitle(""); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося завантажити файл."); }
    finally { setSaving(false); }
  }

  async function toggleCompletion(row: LearningProgress) {
    if (!session || !selectedStudentId) return;
    setError("");
    try {
      await updateStudentLearningProgress(selectedStudentId, row.lesson_id, row.status !== "completed", session);
      setProgress(await loadStudentLearningProgress(selectedStudentId, session));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося оновити прогрес."); }
  }

  async function openFile(lessonId: string, materialId: string, filename: string | null) {
    if (!session) return;
    try {
      const root = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
      const response = await fetch(`${root}${materialFileUrl(lessonId, materialId)}?inline=true`, {
        headers: { Authorization: `Bearer ${session.accessToken}`, "X-Organization-Id": session.organizationId },
      });
      if (!response.ok) throw new Error("Не вдалося відкрити файл.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (blob.type === "application/pdf" || blob.type.startsWith("image/") || blob.type.startsWith("video/")) {
        const anchor = document.createElement("a"); anchor.href = url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.click();
      } else {
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename || "material"; anchor.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося відкрити файл."); }
  }

  const visibleSessions = sessions.filter((lesson) => lesson.status !== "cancelled"
    && (sessionFilter === "all" || lesson.groupId === sessionFilter))
    .sort((a, b) => new Date(b.startsAt).getTime() - new Date(a.startsAt).getTime()).slice(0, 40);

  return <div className="learningPage">
    <section className="panel learningIntro">
      <div><p className="eyebrow">Навчальна програма</p><h2>Уроки та матеріали</h2><p>Додавайте теми поступово. Для кожного заняття можна обрати урок або лишити тему порожньою.</p></div>
      <span className="learningCount">{items.length} {items.length === 1 ? "урок" : "уроків"}</span>
    </section>
    {error && <div className="learningError" role="alert">{error}</div>}
    <div className="learningGrid">
      <section className="panel learningCurriculum">
        <div className="panelHead"><div><p className="eyebrow">Послідовна програма</p><h2>Зміст курсу</h2></div></div>
        {canEdit && <form className="learningLessonForm" onSubmit={submitLesson}>
          <label>Назва уроку<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={240} required placeholder="Наприклад, Основи керування" /></label>
          <label>Короткий план<textarea value={outline} onChange={(event) => setOutline(event.target.value)} rows={2} maxLength={12000} placeholder="Що викладач має пояснити або показати" /></label>
          <div className="learningFormActions"><button className="primary" disabled={saving}>{editingId ? "Зберегти зміни" : "Додати урок"}</button>{editingId && <button type="button" className="search" onClick={() => { setEditingId(null); setTitle(""); setOutline(""); }}>Скасувати</button>}</div>
        </form>}
        {loading ? <div className="emptyState compactEmpty">Завантаження програми…</div> : items.length === 0 ? <div className="emptyState compactEmpty">Програма ще порожня. Додайте перший урок, коли будете готові.</div> : <div className="learningLessonList">
          {items.map((lesson) => <article className="learningLessonCard" id={`curriculum-${lesson.id}`} key={lesson.id}>
            <button className="learningLessonHeading" onClick={() => setOpenLessonId(openLessonId === lesson.id ? null : lesson.id)}><span className="learningPosition">{lesson.position}</span><span><b>{lesson.title}</b><small>{lesson.materials.length} матеріалів</small></span><span className="learningExpand">{openLessonId === lesson.id ? "−" : "+"}</span></button>
            {openLessonId === lesson.id && <div className="learningLessonBody">
              {lesson.outline && <p className="learningOutline">{lesson.outline}</p>}
              <div className="learningMaterials">{lesson.materials.map((material) => <div className="learningMaterial" key={material.id}>
                {material.kind === "link" ? <a href={material.url ?? "#"} target="_blank" rel="noreferrer">↗ {material.title}</a> : <button className="learningTextButton" onClick={() => void openFile(lesson.id, material.id, material.filename)}>↧ {material.title}</button>}
                {canEdit && <button className="learningRemove" aria-label="Видалити матеріал" onClick={async () => { if (session) { await removeMaterial(lesson.id, material.id, session); await refresh(); } }}>×</button>}
              </div>)}{lesson.materials.length === 0 && <small className="muted">До уроку ще не додані матеріали.</small>}</div>
              {canEdit && <div className="learningMaterialAdd">
                <label>Назва матеріалу<input value={materialLessonId === lesson.id ? materialTitle : ""} onChange={(event) => { setMaterialLessonId(lesson.id); setMaterialTitle(event.target.value); }} placeholder="Презентація" /></label>
                <form className="learningLinkForm" onSubmit={addLink}><input aria-label="Посилання на матеріал" value={materialLessonId === lesson.id ? materialUrl : ""} onChange={(event) => { setMaterialLessonId(lesson.id); setMaterialUrl(event.target.value); }} placeholder="https://…" /><button className="search" disabled={saving}>Додати посилання</button></form>
                <label className="learningUpload"><span>Завантажити файл <small>(PDF, PowerPoint, зображення або MP4 · до 20 МБ)</small></span><input type="file" accept=".pdf,.ppt,.pptx,.jpg,.jpeg,.png,.webp,.mp4" onChange={(event) => void addFile(event, lesson.id)} disabled={saving} /></label>
              </div>}
              {canEdit && <div className="learningCardActions"><button className="search" onClick={() => { setEditingId(lesson.id); setTitle(lesson.title); setOutline(lesson.outline ?? ""); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Редагувати урок</button><button className="search dangerText" onClick={async () => { if (session && window.confirm("Видалити урок і його матеріали?")) { try { await removeCurriculumLesson(lesson.id, session); await refresh(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося видалити урок."); } } }}>Видалити</button></div>}
            </div>}
          </article>)}
        </div>}
      </section>

      <div className="learningSide">
        <section className="panel learningPanel">
          <p className="eyebrow">Проведення заняття</p><h2>Обрати тему</h2><p className="muted">Тема вибирається для конкретного заняття. Якщо її немає в програмі, залиште «Без теми» — відвідування все одно збережеться.</p>
          <label>Група<select value={sessionFilter} onChange={(event) => setSessionFilter(event.target.value)}><option value="all">Усі групи</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
          <div className="learningSessionList">{visibleSessions.map((lesson) => <div className="learningSessionRow" key={lesson.id}>
            <div><b>{groups.find((group) => group.id === lesson.groupId)?.name ?? "Група"}</b><small>{new Date(lesson.startsAt).toLocaleDateString("uk-UA", { day: "numeric", month: "short" })} · {new Date(lesson.startsAt).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</small></div>
            <div className="learningSessionTopic"><select aria-label="Тема заняття" value={lesson.curriculumLessonId ?? ""} disabled={!canEdit || !session} onChange={async (event) => {
              if (!session) return;
              try {
                const saved = await assignSessionLesson(lesson.id, event.target.value || null, session);
                window.dispatchEvent(new CustomEvent("crm:learning-session-updated", { detail: { sessionId: lesson.id, lessonId: event.target.value || null, topic: saved.topic } }));
              }
              catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося призначити тему."); }
            }}><option value="">Без теми</option>{items.map((item) => <option key={item.id} value={item.id}>{item.position}. {item.title}</option>)}</select>
              {lesson.curriculumLessonId && <button className="learningTextButton" onClick={() => {
                setOpenLessonId(lesson.curriculumLessonId!);
                window.setTimeout(() => document.getElementById(`curriculum-${lesson.curriculumLessonId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 40);
              }}>Відкрити матеріали уроку ↗</button>}
            </div>
          </div>)}{visibleSessions.length === 0 && <div className="emptyState compactEmpty">Занять не знайдено.</div>}</div>
        </section>

        <section className="panel learningPanel">
          <p className="eyebrow">Поточна група</p><h2>Початковий прогрес</h2><p className="muted">Для групи, яка вже навчалася до запуску CRM, можна одним разом позначити пройдені уроки для її поточних учнів.</p>
          <label>Група<select value={selectedGroupId} onChange={(event) => { setSelectedGroupId(event.target.value); setSelectedStudentId(""); }}><option value="">Оберіть групу</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
          <label>Група вже пройшла уроків<input type="number" min="0" max="10000" value={baseline} onChange={(event) => setBaseline(event.target.value)} /></label>
          <button className="search" disabled={!session || !selectedGroupId || !canEdit} onClick={async () => { try { await setGroupBaseline(selectedGroupId, Number(baseline), session!); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Не вдалося зберегти прогрес групи."); } }}>Зберегти прогрес групи</button>
        </section>

        <section className="panel learningPanel">
          <p className="eyebrow">Індивідуальний прогрес</p><h2>Пройдені та пропущені</h2>
          <label>Учень<select value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}><option value="">Оберіть учня</option>{studentsForGroup.map((student) => <option key={student.id} value={student.id}>{student.name}</option>)}</select></label>
          {selectedStudentId && <div className="learningProgressList">{progress.map((row) => <label className="learningProgressRow" key={row.lesson_id}>
            <span><b>{row.position}. {row.title}</b><small className={`learningStatus ${row.status}`}>{statusLabels[row.status]}</small></span>
            <input type="checkbox" checked={row.status === "completed"} disabled={!canEdit || row.status === "completed" && !row.manual_completion} onChange={() => void toggleCompletion(row)} aria-label={`Позначити урок ${row.title} опрацьованим`} />
          </label>)}{progress.length === 0 && <div className="emptyState compactEmpty">У програмі ще немає уроків.</div>}</div>}
          <small className="muted learningHint">Відвідування заняття з темою автоматично зараховує урок. Позначку можна виправити вручну.</small>
        </section>
      </div>
    </div>
  </div>;
}
