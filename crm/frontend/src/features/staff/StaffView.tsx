import type { LocationDemo } from "../locations/types";
import type { EntityId } from "../leads/model";
import type { StaffDemo } from "./model";

type StaffViewProps = {
  staff: StaffDemo[];
  locations: LocationDemo[];
  onSelectStaff: (staffId: EntityId) => void;
  onInvite: () => void;
  onCreate: () => void;
};

export function StaffView({ staff, locations, onSelectStaff, onInvite, onCreate }: StaffViewProps) {
  const activeStaff = staff.filter((item) => item.isActive);
  const teacherCount = activeStaff.filter((item) => item.role === "Викладач").length;
  const administrationCount = activeStaff.filter((item) =>
    ["Власник", "Адміністратор", "Менеджер"].includes(item.role)
  ).length;

  return <section className="staffLayout">
    <article className="panel staffPanel">
      <div className="panelHead">
        <div><p className="eyebrow">Команда</p><h2>Працівники</h2></div>
        <div className="staffActions">
          <button className="search" onClick={onInvite}>Запросити в CRM</button>
          <button className="primary" onClick={onCreate}>+ Працівник</button>
        </div>
      </div>
      <div className="staffTable">
        <div className="staffRow staffHead"><span>Працівник</span><span>Роль</span><span>Локації</span><span>Групи</span><span>Статус</span></div>
        {staff.map((member) => <button className="staffRow staffButton" key={member.id} onClick={() => onSelectStaff(member.id)}>
          <span className="staffIdentity"><i>{member.fullName[0]}</i><b>{member.fullName}<small>{member.email || member.phone || "Контакти не вказано"}</small></b></span>
          <span>{member.role}</span>
          <span>{member.locationIds.map((id) => locations.find((location) => location.id === id)?.name).filter(Boolean).join(", ") || "—"}</span>
          <span>{member.groupIds.length}</span>
          <span className={"staffStatus " + (member.isActive ? "active" : "inactive")}>{member.isActive ? "Активний" : "Неактивний"}</span>
        </button>)}
      </div>
    </article>
    <aside className="panel staffSummary">
      <p className="eyebrow">Команда</p><h2>{activeStaff.length} активних</h2>
      <div className="summaryMetric"><span>Викладачі</span><strong>{teacherCount}</strong></div>
      <div className="summaryMetric"><span>Адміністрація</span><strong>{administrationCount}</strong></div>
      <div className="summaryMetric"><span>Локацій</span><strong>{locations.filter((item) => item.isActive).length}</strong></div>
    </aside>
  </section>;
}
