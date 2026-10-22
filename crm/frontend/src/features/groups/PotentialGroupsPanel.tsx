import { useEffect, useMemo, useState } from "react";
import { apiEnabled, apiGet, apiPost, apiPut, type Session } from "../../api";
import type { Lead } from "../leads/model";
import { availabilityLabel } from "../leads/availability";
import { TimeSelect, WeekdayPicker } from "../../components/ScheduleEditors";
import { availabilityRanges, availabilitySnapshot, clock, commonSlots, DAYS, generatePotentialGroups, hasAvailabilityChanged, matchSlot, memberKey, slotLabel, suggestedSchedule, toMinutes } from "./potentialMatching";
import type { PotentialGroupProposal, PotentialGroupSlotDraft, PotentialResponse } from "./potentialGroups";

const RESPONSES: Record<PotentialResponse, string> = {
  not_contacted: "Не зв’язувалися", awaiting: "Очікуємо відповідь", agreed: "Погоджено",
  other_time: "Потрібен інший час", reconfirm: "Повторно погодити", declined: "Відмовились від пропозиції",
};
const MATCHES = { preferred: "Підходить за даними", possible: "Допустимий час", approximate: "Уточнити час", conflict: "Не підходить за даними", unknown: "Немає даних про час" };
type Props = {
  waiting: Lead[]; leads: Lead[]; session: Session | null; canManage: boolean;
  onCreateGroup: (studentIds: string[], proposal: PotentialGroupProposal) => void;
};

export function PotentialGroupsPanel({ waiting, leads, session, canManage, onCreateGroup }: Props) {
  const [saved, setSaved] = useState<PotentialGroupProposal[]>([]);
  const [recommendations, setRecommendations] = useState<PotentialGroupProposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tolerance, setTolerance] = useState(0);
  const [ageSpread, setAgeSpread] = useState(3);
  const [expanded, setExpanded] = useState(false);
  const [generated, setGenerated] = useState(false);
  const candidates = (expanded ? leads.filter((l) => !["Відмовились", "Неактуально", "Не відповідає"].includes(l.status)) : waiting)
    .filter((lead) => !lead.groupId && lead.status !== "Зарахований");
  const incomplete = candidates.filter((l) => !l.age || !(l.availability ?? []).some((s) => s.preference !== "avoid"));
  const load = async () => {
    if (!session || !apiEnabled) return;
    setLoading(true);
    try { setSaved(await apiGet<PotentialGroupProposal[]>("/groups/potential-proposals", session)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Не вдалося завантажити пропозиції"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [session?.accessToken, session?.organizationId]);
  const enrolledIds = new Set(leads.filter((lead) => lead.groupId || lead.status === "Зарахований").map((lead) => lead.id));
  const activeSaved = saved.filter((p) => !p.formed_group_id && !p.members.some((member) => enrolledIds.has(member.student_id)));
  const visibleDrafts = recommendations.filter((p) => !activeSaved.some((s) => memberKey(s.members) === memberKey(p.members)));
  const all = [...activeSaved, ...visibleDrafts];
  const generate = () => {
    const now = new Date().toISOString();
    setRecommendations(generatePotentialGroups(candidates, tolerance, ageSpread).map((p) => ({ ...p, id: `draft-${memberKey(p.members)}`, created_at: now, updated_at: now, selected_slots: [], schedule_history: [], version: 1, stale: false })));
    setGenerated(true);
  };
  return <section className="potentialGroupsSection" aria-labelledby="potential-groups-title">
    <div className="potentialGroupsHead"><div><p className="eyebrow">Підбір → графік → погодження → група</p><h2 id="potential-groups-title">Потенційні групи</h2><p>Одна картка — один склад дітей. Оберіть графік, збережіть пропозицію та узгодьте її з батьками.</p></div>
      <button className="primary" disabled={!canManage || loading || !session} onClick={generate}>Підібрати групи</button></div>
    <div className="potentialGroupsMeta"><span>Кандидатів: <b>{candidates.length}</b></span><span>Потрібно уточнити дані: <b>{incomplete.length}</b></span><span>Ціль: <b>6 дітей</b> · максимум 8</span></div>
    <details className="potentialGroupsIncomplete"><summary>Налаштування підбору{expanded ? " · розширений пошук" : " · очікують групу"}</summary><div className="potentialGroupsActions">
      <label>Учні<select value={expanded ? "expanded" : "waiting"} onChange={(e) => setExpanded(e.target.value === "expanded")}><option value="waiting">Очікують групу</option><option value="expanded">Розширити пошук: нові, пробні, відкладені</option></select></label>
      <label>Різниця у віці<select value={ageSpread} onChange={(e) => setAgeSpread(Number(e.target.value))}>{[2, 3, 4].map((n) => <option key={n} value={n}>До {n} років</option>)}</select></label>
      <label>Час<select value={tolerance} onChange={(e) => setTolerance(Number(e.target.value))}><option value={0}>Лише точні збіги</option><option value={1}>Також варіанти в межах ±1 години</option><option value={2}>Також варіанти в межах ±2 годин</option></select></label>
      <small>Після зміни налаштувань натисніть «Підібрати групи». Збережені пропозиції залишаться.</small></div></details>
    {incomplete.length > 0 && <details className="potentialGroupsIncomplete"><summary>Уточнити дані · {incomplete.length}</summary><div>{incomplete.map((l) => <span key={l.id}><b>{l.child}</b><small>{!l.age ? "Вкажіть вік. " : ""}{availabilityLabel(l.availability ?? [])}</small></span>)}</div></details>}
    {error && <div className="registryError" role="alert">{error}</div>}
    {loading && <p role="status">Завантажуємо пропозиції…</p>}
    {generated && !visibleDrafts.length && <p role="status">Нових сумісних складів немає. Збережені пропозиції та відповіді батьків залишились. За потреби розширте пошук.</p>}
    {!loading && !all.length && !generated && <p>Натисніть «Підібрати групи», щоб знайти сумісних дітей.</p>}
    <div className="potentialProposalList">{all.map((p, i) => <ProposalCard key={`${p.id}:${p.version}`} proposal={p} index={i + 1} leads={leads} candidates={candidates} all={all} tolerance={tolerance} canManage={canManage} session={session} onSaved={(updated) => setSaved((items) => [updated, ...items.filter((s) => s.id !== updated.id)])} onCreateGroup={onCreateGroup} />)}</div>
    {saved.some((p) => p.formed_group_id) && <details className="potentialGroupsIncomplete"><summary>Створені з пропозицій групи · {saved.filter((p) => p.formed_group_id).length}</summary><p>Погодження збережені. Створені групи доступні в основному списку вище.</p></details>}
  </section>;
}

type CardProps = Pick<Props, "leads" | "session" | "canManage" | "onCreateGroup"> & { proposal: PotentialGroupProposal; candidates: Lead[]; all: PotentialGroupProposal[]; tolerance: number; index: number; onSaved: (p: PotentialGroupProposal) => void };
function ProposalCard({ proposal, leads, candidates, all, tolerance, index, session, canManage, onSaved, onCreateGroup }: CardProps) {
  const [members, setMembers] = useState(proposal.members);
  const [selected, setSelected] = useState(proposal.selected_slots ?? []);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [previewError, setPreviewError] = useState("");
  const [checking, setChecking] = useState(false);
  const leadById = useMemo(() => new Map(leads.map((l) => [l.id, l])), [leads]);
  const children = members.map((m) => leadById.get(m.student_id)).filter((l): l is Lead => Boolean(l));
  const slots = useMemo(() => commonSlots(children, tolerance), [JSON.stringify(children.map((l) => [l.id, l.availability])), tolerance]);
  const ranges = availabilityRanges(slots);
  const exactRanges = ranges.filter((r) => r.exact_match);
  const approximateRanges = ranges.filter((r) => !r.exact_match);
  const isNew = proposal.id.startsWith("draft-");
  const dirty = JSON.stringify(members) !== JSON.stringify(proposal.members) || JSON.stringify(selected) !== JSON.stringify(proposal.selected_slots ?? []);
  const stale = proposal.stale || members.some((m) => hasAvailabilityChanged(m.availability_snapshot, leadById.get(m.student_id)));
  const locations = [...new Set(children.map((l) => l.preferredLocationId).filter(Boolean))];
  const locationId = locations.length === 1 ? locations[0] : null;
  const ages = children.map((l) => l.age).filter(Boolean);
  const eligibleAgreed = members.filter((m) => m.response === "agreed" && leadById.get(m.student_id)?.status === "Очікує групу").map((m) => m.student_id);
  const ready = selected.length >= 2 && new Set(selected.map((s) => s.weekday)).size === selected.length;
  useEffect(() => {
    if (!session || !selected.length) { setConflicts([]); setPreviewError(""); setChecking(false); return; }
    let cancelled = false;
    setChecking(true);
    const timer = window.setTimeout(() => {
      void apiPost<string[]>("/groups/potential-proposals/preview", { location_id: locationId, slots: selected }, session).then((items) => { if (!cancelled) { setConflicts(items); setPreviewError(""); } }).catch((e) => { if (!cancelled) setPreviewError(e instanceof Error ? e.message : "Не вдалося перевірити конфлікти"); }).finally(() => { if (!cancelled) setChecking(false); });
    }, 300);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [JSON.stringify(selected), locationId, session?.accessToken]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const changeSchedule = (next: PotentialGroupSlotDraft[]) => {
    setSelected(next);
    setMembers((items) => items.map((m) => m.response === "agreed" ? { ...m, response: "reconfirm" } : m));
  };
  const save = async () => {
    if (!session) return;
    setBusy(true); setError("");
    try {
      const payload = { version: isNew ? undefined : proposal.version, members: members.map((m) => ({ ...m, availability_snapshot: leadById.get(m.student_id) ? availabilitySnapshot(leadById.get(m.student_id)!) : m.availability_snapshot })), slots: slots.length ? slots : proposal.slots, selected_slots: selected, stale: false };
      const result = isNew ? await apiPost<PotentialGroupProposal>("/groups/potential-proposals", payload, session) : await apiPut<PotentialGroupProposal>(`/groups/potential-proposals/${proposal.id}`, payload, session);
      onSaved(result);
    } catch (e) { setError(e instanceof Error ? e.message : "Не вдалося зберегти пропозицію"); }
    finally { setBusy(false); }
  };
  const fit = (lead: Lead | undefined) => {
    const states = selected.map((s) => matchSlot(lead, s, 2));
    return states.includes("conflict") ? "conflict" : states.includes("unknown") || !states.length ? "unknown" : states.includes("approximate") ? "approximate" : states.includes("possible") ? "possible" : "preferred";
  };
  return <article className={`potentialProposal${stale ? " stale" : ""}`} data-testid="potential-proposal">
    <div className="potentialProposalHead"><div><span className="potentialProposalNumber">{isNew ? "Рекомендація" : "Пропозиція"} {index}</span><h3>{members.length} дітей{ages.length ? ` · ${Math.min(...ages)}–${Math.max(...ages)} років` : ""}</h3><small role="status">{dirty ? "Є незбережені зміни" : isNew ? "Ще не збережена" : "Збережено"}{stale ? " · побажання змінилися" : ""}</small></div></div>
    <div className="potentialRanges"><b>Спільна доступність</b>{exactRanges.length ? exactRanges.map((r) => <span key={slotLabel(r)}>{slotLabel(r)}</span>) : <span>Точного спільного часу немає.</span>}{approximateRanges.length > 0 && <details><summary>Варіанти, які потрібно уточнити</summary>{approximateRanges.map((r) => <p key={slotLabel(r)}>{slotLabel(r)}</p>)}</details>}<small>У межах проміжку оберіть заняття тривалістю 1 година.</small></div>
    {locations.length > 1 && <p className="potentialProposalWarning">Бажані локації відрізняються — узгодьте місце з батьками.</p>}
    <div className="potentialSelected"><b>Обраний графік</b>{selected.length ? selected.map((s, i) => <span key={i}>{slotLabel(s)}</span>) : <span>Ще не обрано</span>}{selected.length < 2 && <small className="potentialProposalWarning">{selected.length ? "Потрібен другий день" : "Оберіть два дні для занять двічі на тиждень"}</small>}
      <button className="search" disabled={!canManage || busy} onClick={() => { if (!selected.length) changeSchedule(suggestedSchedule(slots)); setEditing(!editing); }}>{editing ? "Згорнути редагування" : selected.length ? "Редагувати графік" : "Обрати графік"}</button></div>
    {editing && <fieldset disabled={!canManage || busy} className="potentialScheduleEditor"><div className="potentialProposalSlots">{selected.map((slot, i) => <div className="potentialProposalSlot" key={i}>
      <WeekdayPicker value={slot.weekday} onChange={(weekday) => changeSchedule(selected.map((s, j) => j === i ? { ...s, weekday, exact_match: false } : s))} />
      <TimeSelect label="Початок" value={slot.start_time.slice(0, 5)} onChange={(start_time) => { if (toMinutes(start_time) > 1379) { setError("Оберіть початок до 23:00, щоб заняття завершилося цього дня"); return; } setError(""); changeSchedule(selected.map((s, j) => j === i ? { ...s, start_time, end_time: clock(toMinutes(start_time) + 60), exact_match: false } : s)); }} />
      <span>До {slot.end_time.slice(0, 5)} <button className="link" aria-label={`Прибрати ${DAYS[slot.weekday]}`} onClick={() => changeSchedule(selected.filter((_, j) => j !== i))}>×</button></span>
    </div>)}</div>{selected.length < 7 && <button className="search" onClick={() => { const weekday = DAYS.findIndex((_, d) => !selected.some((s) => s.weekday === d)); changeSchedule([...selected, { weekday, start_time: "17:00", end_time: "18:00", exact_match: false }]); }}>+ Додати день</button>}</fieldset>}
    {selected.length > 0 && <div className="potentialFitSummary"><span>Підходить: {children.filter((l) => ["preferred", "possible"].includes(fit(l))).length}</span><span>Уточнити: {children.filter((l) => ["approximate", "unknown"].includes(fit(l))).length}</span><span>Не підходить: {children.filter((l) => fit(l) === "conflict").length}</span><small>Збіг із побажаннями не замінює підтвердження батьків.</small></div>}
    {checking && <small role="status">Перевіряємо зайнятість локації…</small>}{previewError && <p className="registryError">{previewError}</p>}{conflicts.length > 0 && <details className="potentialConflict" open><summary>Конфлікти розкладу · {conflicts.length}</summary>{conflicts.map((c) => <p key={c}>{c}</p>)}</details>}
    <details className="potentialPeople"><summary>Учні та відповіді батьків · погоджено {members.filter((m) => m.response === "agreed").length}/{members.length}</summary>
      <fieldset disabled={!canManage || busy} className="potentialProposalMembers">{members.map((member) => {
        const lead = leadById.get(member.student_id);
        const others = all.filter((p) => p.id !== proposal.id && p.members.some((m) => m.student_id === member.student_id));
        return <div className="potentialProposalMember" key={member.student_id}><span><b>{lead?.child ?? "Учня немає в поточному списку"} {lead?.age ? `· ${lead.age} р.` : ""}</b><small>{lead?.status}{lead?.deferredUntil ? " · відкладена заявка" : ""}{lead?.preferredLocationName ? ` · ${lead.preferredLocationName}` : ""}</small><small>{lead ? availabilityLabel(lead.availability ?? []) : "Уточніть стан заявки"}</small>
          {selected.length > 0 && <small className={`potentialFit ${fit(lead)}`}>{MATCHES[fit(lead)]}{selected.filter((s) => !["preferred", "possible"].includes(matchSlot(lead, s))).map((s) => ` · ${slotLabel(s)}`).join("")}</small>}{others.length > 0 && <small>Також у {others.length} інших пропозиціях{others.some((p) => p.members.some((m) => m.student_id === member.student_id && m.response === "agreed")) ? " · є погодження" : ""}</small>}</span>
          <label>Відповідь батьків<select aria-label={`Відповідь батьків: ${lead?.child ?? "учень"}`} value={member.response} onChange={(e) => setMembers(members.map((m) => m.student_id === member.student_id ? { ...m, response: e.target.value as PotentialResponse } : m))}>{Object.entries(RESPONSES).map(([v, label]) => <option key={v} value={v} disabled={v === "agreed" && (!ready || stale || isNew || JSON.stringify(selected) !== JSON.stringify(proposal.selected_slots))}>{label}</option>)}</select></label>
          <label className="potentialMemberNote">Побажання / коментар<input maxLength={500} value={member.note ?? ""} onChange={(e) => setMembers(members.map((m) => m.student_id === member.student_id ? { ...m, note: e.target.value } : m))} placeholder={member.response === "other_time" ? "Який день і час підходять?" : "За потреби"} /></label>
          {members.length > 1 && <button className="link danger" onClick={() => setMembers(members.filter((m) => m.student_id !== member.student_id))}>Прибрати з пропозиції</button>}</div>;
      })}</fieldset>
      {members.length < 8 && <label className="potentialProposalAdd">Додати учня<select disabled={!canManage || busy} value="" onChange={(e) => { const lead = leadById.get(e.target.value); if (lead) setMembers([...members, { student_id: lead.id, response: "not_contacted", availability_snapshot: availabilitySnapshot(lead) }]); }}><option value="">Оберіть кандидата</option>{candidates.filter((l) => !members.some((m) => m.student_id === l.id)).map((l) => <option key={l.id} value={l.id}>{l.child} · {l.age} р. · {l.status}</option>)}</select></label>}
      <small>Відмова стосується лише цієї пропозиції. Для зарахування переведіть погоджених дітей у «Очікує групу».</small>
    </details>
    {proposal.schedule_history?.length > 0 && <details className="potentialPeople"><summary>Історія графіка й погоджень · {proposal.schedule_history.length}</summary>{[...proposal.schedule_history].reverse().map((h, i) => <p key={i}><b>{new Date(h.at).toLocaleString("uk-UA")}</b><br />Було: {h.before.map(slotLabel).join("; ") || "не обрано"}<br />Стало: {h.after.map(slotLabel).join("; ") || "не обрано"}{h.after_responses?.filter((r) => r.response !== h.responses?.find((p) => p.student_id === r.student_id)?.response).map((r) => <span className="potentialHistoryResponse" key={r.student_id}>{leadById.get(r.student_id)?.child ?? "Учень"}: {RESPONSES[h.responses?.find((p) => p.student_id === r.student_id)?.response ?? "not_contacted"]} → {RESPONSES[r.response]}</span>)}</p>)}</details>}
    {error && <p className="registryError" role="alert">{error}</p>}
    <div className="potentialProposalFooter"><button className="search" disabled={!canManage || busy || (!dirty && !stale && !isNew) || !selected.length || new Set(selected.map((s) => s.weekday)).size !== selected.length} onClick={() => void save()}>{busy ? "Зберігаємо…" : stale ? "Перевірити й зберегти" : "Зберегти пропозицію"}</button>
      <button className="primary compact" disabled={!canManage || busy || isNew || dirty || stale || !ready || eligibleAgreed.length < 2 || checking || Boolean(previewError) || conflicts.length > 0} onClick={() => onCreateGroup(eligibleAgreed, proposal)}>Створити групу · {eligibleAgreed.length} погоджених</button></div>
    {dirty && <small className="potentialProposalWarning">Збережіть зміни перед створенням групи.</small>}
  </article>;
}
