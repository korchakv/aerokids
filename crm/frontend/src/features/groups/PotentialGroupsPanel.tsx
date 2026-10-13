import { useEffect, useMemo, useState } from "react";
import { apiEnabled, apiGet, apiPost, apiPut, type Session } from "../../api";
import type { Lead } from "../leads/model";
import { availabilityLabel } from "../leads/availability";
import { TimeSelect, WeekdayPicker } from "../../components/ScheduleEditors";
import { findSharedDayNeedsCoordination, generatePotentialGroups, hasAvailabilityChanged } from "./potentialMatching";
import type { PotentialGroupMemberDraft, PotentialGroupProposal, PotentialGroupSlotDraft, PotentialResponse } from "./potentialGroups";

const DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя"];
const RESPONSE_LABEL: Record<PotentialResponse, string> = {
  not_contacted: "Не контактували",
  awaiting: "Очікуємо відповідь",
  agreed: "Погодились",
  declined: "Відмовились від пропозиції",
};
const SHIFT_LABEL: Record<NonNullable<Lead["schoolShift"]>, string> = { first: "І зміна", second: "ІІ зміна", other: "Інше" };
type Props = {
  waiting: Lead[];
  leads: Lead[];
  session: Session | null;
  canManage: boolean;
  onCreateGroup: (studentIds: string[]) => void;
};
type ProposalPayload = Pick<PotentialGroupProposal, "members" | "slots" | "stale">;

function sortProposals(items: PotentialGroupProposal[]) {
  return [...items].sort((a, b) => b.members.length - a.members.length || b.slots.filter((slot) => slot.exact_match).length - a.slots.filter((slot) => slot.exact_match).length || a.created_at.localeCompare(b.created_at));
}

export function PotentialGroupsPanel({ waiting, leads, session, canManage, onCreateGroup }: Props) {
  const [proposals, setProposals] = useState<PotentialGroupProposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [toleranceHours, setToleranceHours] = useState(2);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const leadById = useMemo(() => new Map(leads.map((lead) => [lead.id, lead])), [leads]);
  const notEligible = waiting.filter((lead) => !(lead.availability ?? []).some((slot) => slot.preference !== "avoid"));
  const needsCoordination = useMemo(() => findSharedDayNeedsCoordination(waiting, toleranceHours), [waiting, toleranceHours]);

  const load = async () => {
    if (!apiEnabled || !session) return;
    setLoading(true);
    setError("");
    try {
      const result = await apiGet<PotentialGroupProposal[]>("/groups/potential-proposals", session);
      setProposals(sortProposals(result));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не вдалося завантажити чернетки потенційних груп.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [session?.accessToken, session?.organizationId]);

  useEffect(() => {
    if (!session || loading || proposals.length === 0) return;
    const stale = proposals.filter((proposal) => !proposal.stale && proposal.members.some((member) => hasAvailabilityChanged(member.availability_snapshot, leadById.get(member.student_id))));
    if (!stale.length) return;
    let cancelled = false;
    void (async () => {
      for (const proposal of stale) {
        try {
          const payload = { members: proposal.members, slots: proposal.slots, stale: true };
          const updated = await apiPut<PotentialGroupProposal>(`/groups/potential-proposals/${proposal.id}`, payload, session);
          if (!cancelled) setProposals((items) => sortProposals(items.map((item) => item.id === updated.id ? updated : item)));
        } catch { /* Keep the local stale indicator visible; a later edit can retry persistence. */ }
      }
    })();
    return () => { cancelled = true; };
  }, [session?.accessToken, loading, proposals, leadById]);

  const persist = async (proposal: PotentialGroupProposal, payload: ProposalPayload) => {
    if (!session) return;
    setSavingId(proposal.id);
    setError("");
    try {
      const updated = await apiPut<PotentialGroupProposal>(`/groups/potential-proposals/${proposal.id}`, payload, session);
      setProposals((items) => sortProposals(items.map((item) => item.id === updated.id ? updated : item)));
      setMessage("Чернетку збережено.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не вдалося зберегти зміни.");
    } finally {
      setSavingId(null);
    }
  };

  const generate = async () => {
    if (!session) return;
    setGenerating(true);
    setError("");
    setMessage("");
    try {
      const generated = generatePotentialGroups(waiting, toleranceHours).slice(0, 12);
      if (!generated.length) {
        setMessage("Поки немає двох дітей зі спільним днем і часом. Перевірте побажання в картках учнів.");
        return;
      }
      const created = await Promise.all(generated.map((item) => apiPost<PotentialGroupProposal>("/groups/potential-proposals", { ...item, stale: false }, session)));
      setProposals((items) => sortProposals([...created, ...items]));
      setMessage(`Створено ${created.length} чернеток. Попередні пропозиції збережені.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не вдалося створити потенційні групи.");
    } finally {
      setGenerating(false);
    }
  };

  const updateLocal = (proposalId: string, transform: (item: PotentialGroupProposal) => PotentialGroupProposal) => {
    setProposals((items) => sortProposals(items.map((item) => item.id === proposalId ? transform(item) : item)));
    setMessage("Є незбережені зміни в чернетці.");
  };

  const updateMember = (proposal: PotentialGroupProposal, studentId: string, response: PotentialResponse) => {
    const nextMembers = proposal.members.map((member) => member.student_id === studentId ? { ...member, response } : member);
    const payload = { members: nextMembers, slots: proposal.slots, stale: proposal.stale };
    if (response === "agreed") {
      // Once the family accepts one option, remove them from every other alternative.
      const otherUpdates = proposals.filter((item) => item.id !== proposal.id && item.members.some((member) => member.student_id === studentId));
      for (const other of otherUpdates) {
        const kept = other.members.filter((member) => member.student_id !== studentId);
        if (session) void apiPut<PotentialGroupProposal>(`/groups/potential-proposals/${other.id}`, { members: kept, slots: other.slots, stale: other.stale }, session)
          .then((updated) => setProposals((items) => items.map((item) => item.id === updated.id ? updated : item)))
          .catch(() => setError("Погодження збережено, але не вдалося прибрати учня з усіх альтернатив."));
        updateLocal(other.id, (item) => ({ ...item, members: kept }));
      }
    }
    updateLocal(proposal.id, (item) => ({ ...item, members: nextMembers }));
    if (session) void apiPut<PotentialGroupProposal>(`/groups/potential-proposals/${proposal.id}`, payload, session)
      .then((updated) => {
        setProposals((items) => sortProposals(items.map((item) => item.id === updated.id ? updated : item)));
        setMessage("Відповідь збережена.");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Не вдалося зберегти відповідь батьків."));
  };

  const updateSlot = (proposalId: string, index: number, field: "start_time" | "end_time", value: string) => {
    updateLocal(proposalId, (proposal) => ({ ...proposal, slots: proposal.slots.map((slot, i) => i === index ? { ...slot, [field]: value, exact_match: false } : slot), stale: proposal.stale }));
  };

  const removeMember = (proposal: PotentialGroupProposal, studentId: string) => {
    if (proposal.members.length <= 1) return;
    updateLocal(proposal.id, (item) => ({ ...item, members: item.members.filter((member) => member.student_id !== studentId) }));
  };

  const addMember = (proposal: PotentialGroupProposal, studentId: string) => {
    if (!studentId || proposal.members.length >= 8 || proposal.members.some((member) => member.student_id === studentId)) return;
    const lead = leadById.get(studentId);
    if (!lead) return;
    const member: PotentialGroupMemberDraft = { student_id: lead.id, response: "not_contacted", availability_snapshot: lead.availability ?? [] };
    updateLocal(proposal.id, (item) => ({ ...item, members: [...item.members, member] }));
  };

  const updateSlotDay = (proposalId: string, index: number, weekday: number) => {
    updateLocal(proposalId, (item) => ({ ...item, slots: item.slots.map((slot, i) => i === index ? { ...slot, weekday, exact_match: false } : slot), stale: item.stale }));
  };

  return <section className="potentialGroupsSection" aria-labelledby="potential-groups-title">
    <div className="potentialGroupsHead">
      <div><p className="eyebrow">Підбір за доступністю</p><h2 id="potential-groups-title">Потенційні групи <span>{proposals.length}</span></h2>
        <p>Розподіліть учнів, які очікують групу, за спільними днями й орієнтовним часом. Пропозиції залишаються чернетками, доки ви не створите реальну групу.</p></div>
      <div className="potentialGroupsActions"><label>Допуск часу<select value={toleranceHours} onChange={(event) => setToleranceHours(Number(event.target.value))}><option value={0}>Точний час</option><option value={1}>±1 година</option><option value={2}>±2 години</option><option value={3}>±3 години</option><option value={4}>±4 години</option></select></label><button className="primary" onClick={() => void generate()} disabled={!canManage || generating || loading || !apiEnabled || !session}>{generating ? "Підбираємо…" : "Сформувати потенційні групи"}</button></div>
    </div>
    <div className="potentialGroupsMeta"><span>Учнів очікують групу: <b>{waiting.length}</b></span><span>З графіком: <b>{waiting.length - notEligible.length}</b></span><span>Без графіка: <b>{notEligible.length}</b></span><span>Спільний день, час узгодити: <b>{needsCoordination.length}</b></span><small>Ціль — 6 дітей, максимум — 8. Час орієнтовний, допуск підбору ±{toleranceHours} години.</small></div>
    {!apiEnabled && <div className="registryError">Збереження потенційних груп доступне після підключення CRM до API.</div>}
    {error && <div className="registryError" role="alert">{error}</div>}
    {message && <div className="potentialGroupsMessage" role="status">{message}</div>}
    {notEligible.length > 0 && <details className="potentialGroupsIncomplete"><summary>Уточнити графік для {notEligible.length} учнів</summary><div>{notEligible.map((lead) => <span key={lead.id}><b>{lead.child}</b><small>{lead.schoolShift ? `Шкільна зміна: ${SHIFT_LABEL[lead.schoolShift]} · уточніть у батьків точний час · ` : ""}{availabilityLabel(lead.availability ?? [])}</small></span>)}</div></details>}
    {needsCoordination.length > 0 && <details className="potentialGroupsCoordination"><summary>Спільний день є, але в межах допуску немає спільного часу · {needsCoordination.length} пар</summary><div>{needsCoordination.slice(0, 30).map(([first, second]) => <span key={`${first.id}-${second.id}`}><b>{first.child} + {second.child}</b><small>{availabilityLabel(first.availability ?? [])} · {availabilityLabel(second.availability ?? [])}</small></span>)}</div></details>}
    {loading && <p className="muted">Завантаження збережених чернеток…</p>}
    {!loading && proposals.length === 0 && <div className="potentialGroupsEmpty">Натисніть «Сформувати потенційні групи», щоб переглянути можливі набори.</div>}
    <div className="potentialProposalList">
      {proposals.map((proposal, index) => {
        const agreedIds = proposal.members.filter((member) => member.response === "agreed").map((member) => member.student_id);
        const eligibleAgreedIds = agreedIds.filter((studentId) => leadById.get(studentId)?.status === "Очікує групу");
        const canCreate = eligibleAgreedIds.length >= 2;
        const stale = proposal.stale || proposal.members.some((member) => hasAvailabilityChanged(member.availability_snapshot, leadById.get(member.student_id)));
        const dayNames = proposal.slots.map((slot) => DAYS[slot.weekday]).filter((day, i, all) => all.indexOf(day) === i);
        return <article className={`potentialProposal${stale ? " stale" : ""}`} key={proposal.id}>
          <div className="potentialProposalHead"><div><span className="potentialProposalNumber">Чернетка {index + 1}</span><b>{proposal.members.length} дітей · {dayNames.join(" / ")}</b><small>{stale ? "Побажання змінилися — перевірте пропозицію" : "Чернетка збережена"}</small>{dayNames.length === 1 && <small>Є спільний день; другий день для занять двічі на тиждень ще потрібно узгодити.</small>}</div><button className="link" disabled={!canManage || savingId === proposal.id} onClick={() => void persist(proposal, { members: proposal.members, slots: proposal.slots, stale })}>{savingId === proposal.id ? "Зберігаємо…" : "Зберегти зміни"}</button></div>
          <small className="potentialProposalTimeHint">Орієнтовні варіанти для узгодження; постійний розклад групи створюється окремо в «Розкладі».</small>
          <div className="potentialProposalSlots">{proposal.slots.map((slot, slotIndex) => <div className="potentialProposalSlot" key={`${slot.weekday}-${slotIndex}`}>
            <WeekdayPicker value={slot.weekday} disabled={!canManage} onChange={(value) => updateSlotDay(proposal.id, slotIndex, value)} />
            <TimeSelect label="Початок" value={slot.start_time} disabled={!canManage} onChange={(value) => updateSlot(proposal.id, slotIndex, "start_time", value)} />
            <TimeSelect label="Завершення" value={slot.end_time} disabled={!canManage} onChange={(value) => updateSlot(proposal.id, slotIndex, "end_time", value)} />
            <small>{slot.exact_match ? "Є спільний точний час" : "Час потребує узгодження"}</small>
          </div>)}</div>
          <div className="potentialProposalMembers">{proposal.members.map((member) => {
            const lead = leadById.get(member.student_id);
            return <div className="potentialProposalMember" key={member.student_id}>
              <span><b>{lead?.child ?? "Учня не знайдено"}</b><small>{lead ? availabilityLabel(lead.availability ?? []) : "Відсутній у поточному списку"}</small></span>
              <select aria-label={`Відповідь сім’ї: ${lead?.child ?? "учень"}`} value={member.response} disabled={!canManage} onChange={(event) => updateMember(proposal, member.student_id, event.target.value as PotentialResponse)}>{Object.entries(RESPONSE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
              {canManage && proposal.members.length > 1 && <button className="link danger" aria-label={`Прибрати ${lead?.child ?? "учня"}`} onClick={() => removeMember(proposal, member.student_id)}>×</button>}
            </div>;
          })}</div>
          {canManage && proposal.members.length < 8 && <label className="potentialProposalAdd">Додати учня<select defaultValue="" onChange={(event) => { addMember(proposal, event.target.value); event.currentTarget.value = ""; }}><option value="">Оберіть зі списку «Очікує групу»</option>{waiting.filter((lead) => !proposal.members.some((member) => member.student_id === lead.id)).map((lead) => <option key={lead.id} value={lead.id}>{lead.child}</option>)}</select></label>}
          {proposal.members.length < 2 && <small className="potentialProposalWarning">Після погодження учня в інших пропозиціях лишився один учасник. Додайте іншого кандидата або залиште чернетку без зарахування.</small>}
          <div className="potentialProposalFooter"><span>Погодились: <b>{agreedIds.length}</b>{eligibleAgreedIds.length !== agreedIds.length && <> · очікують групу: <b>{eligibleAgreedIds.length}</b></>} · для створення потрібно від 2{canCreate && eligibleAgreedIds.length < 6 ? " · менше за ціль 6" : ""}</span><button className="primary compact" disabled={!canManage || !canCreate} onClick={() => onCreateGroup(eligibleAgreedIds)}>Створити групу з погодженими</button></div>
        </article>;
      })}
    </div>
  </section>;
}
