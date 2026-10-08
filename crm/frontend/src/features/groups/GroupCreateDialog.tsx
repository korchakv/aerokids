import type { Dispatch, SetStateAction } from "react";
import { ScheduleSlotEditor, type DraftScheduleSlot } from "../../components/ScheduleEditors";
import type { LocationDemo } from "../locations/types";
import type { StaffDemo } from "../staff/model";
import { candidateCompatibility } from "./matching";
import { hasDuplicateSlots } from "./helpers";
import type { EntityId, Lead } from "../leads/model";

type Setter<T> = Dispatch<SetStateAction<T>>;
type MaybePromise = void | Promise<void>;

export type GroupCreateDialogProps = {
  open: boolean;
  groupName: string;
  groupCapacity: number;
  groupLocationId: EntityId | "";
  newGroupTeacherId: EntityId | "";
  groupSchedule: DraftScheduleSlot[];
  groupCreateError: string;
  selectedCandidates: EntityId[];
  leads: Lead[];
  activeLocations: LocationDemo[];
  activeTeachers: StaffDemo[];
  canManageStaff: boolean;
  setOpen: Setter<boolean>;
  setGroupName: Setter<string>;
  setGroupCapacity: Setter<number>;
  setGroupLocationId: Setter<EntityId | "">;
  setNewGroupTeacherId: Setter<EntityId | "">;
  setGroupSchedule: Setter<DraftScheduleSlot[]>;
  setGroupCreateError: Setter<string>;
  onCreateLocation: () => void;
  onCreateGroup: () => MaybePromise;
};

export function GroupCreateDialog({
  open,
  groupName,
  groupCapacity,
  groupLocationId,
  newGroupTeacherId,
  groupSchedule,
  groupCreateError,
  selectedCandidates,
  leads,
  activeLocations,
  activeTeachers,
  canManageStaff,
  setOpen,
  setGroupName,
  setGroupCapacity,
  setGroupLocationId,
  setNewGroupTeacherId,
  setGroupSchedule,
  setGroupCreateError,
  onCreateLocation,
  onCreateGroup,
}: GroupCreateDialogProps) {
  if (!open) return null;

  return <div className="modalBackdrop">
    <div className="groupModal groupCreateModal" data-testid="group-create-dialog" onClick={(event) => event.stopPropagation()}>
      <button className="drawerClose" aria-label="Закрити створення групи" onClick={() => setOpen(false)}>×</button>
      <p className="eyebrow">Нова група</p>
      <h2>Створити групу</h2>
      <p className="modalIntro">{selectedCandidates.length
        ? `Буде зараховано ${selectedCandidates.length} ${selectedCandidates.length === 1 ? "учня" : "учнів"}. Їх можна змінити пізніше.`
        : "Групу можна створити наперед без учнів. Розклад, викладача й учасників можна змінювати пізніше."}</p>
      <label>Назва групи<input autoFocus value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="Наприклад: FPV Start 8–10" /></label>
      <div className="formTwo">
        <label>Місткість<input type="number" min={1} max={100} value={groupCapacity} onChange={(event) => setGroupCapacity(Number(event.target.value))} /></label>
        {activeLocations.length === 0
          ? <div className="groupLocationOptional">
              <b>Локація <small>(необов’язково)</small></b>
              <small>Групу можна створити без локації та вказати її пізніше.</small>
              <button className="search" type="button" onClick={onCreateLocation}>+ Створити локацію</button>
            </div>
          : activeLocations.length === 1
            ? <label>Локація <small>(необов’язково)</small><select value={groupLocationId} onChange={(event) => setGroupLocationId(event.target.value)}>
                <option value="">Без локації</option>
                <option value={activeLocations[0].id}>{activeLocations[0].name}</option>
              </select></label>
            : <label>Локація <small>(необов’язково)</small><select value={groupLocationId} onChange={(event) => { setGroupLocationId(event.target.value); setGroupCreateError(""); }}>
                <option value="">Без локації</option>
                {activeLocations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
              </select></label>}
      </div>
      {canManageStaff && <label>Викладач <small>(необов’язково)</small><select value={newGroupTeacherId} onChange={(event) => setNewGroupTeacherId(event.target.value)}>
        <option value="">Призначити пізніше</option>
        {activeTeachers.map((teacher) => <option value={teacher.id} key={teacher.id}>{teacher.fullName}</option>)}
      </select></label>}
      <div className="groupCreateScheduleHead"><div><b>Регулярний розклад</b><small>Це шаблон: конкретні заняття з’являтимуться в календарі автоматично.</small></div></div>
      <ScheduleSlotEditor value={groupSchedule} onChange={setGroupSchedule} />
      {selectedCandidates.length > 0 && <div className="selectedNames">{leads.filter((lead) => selectedCandidates.includes(lead.id)).map((lead) => {
        const compatibility = candidateCompatibility(lead, groupSchedule, groupLocationId || null);
        return <span className={"candidateCompatibility " + compatibility.state} key={lead.id}>
          <b>{lead.child} · {lead.age}</b><small>{compatibility.icon} {compatibility.label}</small><small>{compatibility.detail}</small>
        </span>;
      })}</div>}
      {groupCreateError && <div className="groupCreateError">{groupCreateError}</div>}
      <button className="primary full" disabled={!groupName.trim() || selectedCandidates.length > groupCapacity || hasDuplicateSlots(groupSchedule)} onClick={() => void onCreateGroup()}>
        {!groupName.trim() ? "Вкажіть назву групи" : selectedCandidates.length > groupCapacity ? "Збільште місткість групи" : hasDuplicateSlots(groupSchedule) ? "Приберіть однакові слоти" : selectedCandidates.length ? "Створити групу і зарахувати" : "Створити групу"}
      </button>
    </div>
  </div>;
}
