import type { GroupItem } from "../groups/types";
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


type StaffDrawerProps = {
  staff: StaffDemo;
  locations: LocationDemo[];
  groups: GroupItem[];
  apiEnabled: boolean;
  resetLink: string;
  onClose: () => void;
  onToggleTeaching: (next: boolean) => void | Promise<void>;
  onToggleLocation: (locationId: EntityId) => void | Promise<void>;
  onToggleGroup: (groupId: EntityId) => void | Promise<void>;
  onToggleActive: () => void | Promise<void>;
  onCreatePasswordReset: () => void | Promise<void>;
};

export function StaffDrawer({
  staff,
  locations,
  groups,
  apiEnabled,
  resetLink,
  onClose,
  onToggleTeaching,
  onToggleLocation,
  onToggleGroup,
  onToggleActive,
  onCreatePasswordReset,
}: StaffDrawerProps) {
  const canTeach = staff.canTeach || staff.role === "Викладач";
  return <div className="drawerBackdrop" onClick={onClose}>
    <aside className="drawer studentDrawer" onClick={(event) => event.stopPropagation()}>
      <button className="drawerClose" onClick={onClose}>×</button>
      <p className="eyebrow">Працівник</p>
      <div className="studentHero">
        <span>{staff.fullName[0]}</span>
        <div><h2>{staff.fullName}</h2><p>{staff.role}{staff.canTeach ? " · Викладає" : ""}</p></div>
      </div>
      <div className="contactCard">
        <span>Контакти</span>
        <b>{staff.email || "Email не вказано"}</b>
        <a href={"tel:" + staff.phone.replace(/\s/g, "")}>{staff.phone || "Телефон не вказано"}</a>
      </div>
      <div className="studentSection">
        <h3>Обов’язки</h3>
        <label className="toggleRow responsibilityToggle">
          <input
            type="checkbox"
            checked={canTeach}
            disabled={staff.role === "Викладач"}
            onChange={(event) => void onToggleTeaching(event.target.checked)}
          />
          <span><b>Може викладати</b><small>Можна призначати викладачем груп незалежно від ролі доступу.</small></span>
        </label>
      </div>
      <div className="studentSection">
        <h3>Локації</h3>
        <div className="assignmentList">{locations.map((location) =>
          <label key={location.id}>
            <input
              type="checkbox"
              checked={staff.locationIds.includes(location.id)}
              onChange={() => void onToggleLocation(location.id)}
            />
            <span>{location.name}<small>{location.address}</small></span>
          </label>
        )}</div>
      </div>
      <div className="studentSection">
        <h3>Групи</h3>
        {!canTeach && <div className="formNotice">Щоб призначати групи, увімкніть обов’язок «Може викладати».</div>}
        <div className="assignmentList">{groups.map((group) =>
          <label key={group.id} className={!canTeach ? "assignmentDisabled" : ""}>
            <input
              type="checkbox"
              disabled={!canTeach}
              checked={staff.groupIds.includes(group.id)}
              onChange={() => void onToggleGroup(group.id)}
            />
            <span>{group.name}<small>{group.schedule}</small></span>
          </label>
        )}</div>
      </div>
      <div className="studentSection">
        <h3>Статус</h3>
        <button className="search full" onClick={() => void onToggleActive()}>
          {staff.isActive ? "Деактивувати працівника" : "Активувати працівника"}
        </button>
      </div>
      {apiEnabled && staff.email && <div className="studentSection">
        <h3>Доступ до CRM</h3>
        {!resetLink ? <button className="search full" onClick={() => void onCreatePasswordReset()}>Створити посилання для нового пароля</button> : <div className="inviteSuccess">
          <b>Посилання готове</b>
          <p>Воно одноразове та діє 1 годину. Надішліть його працівнику приватно.</p>
          <code>{resetLink}</code>
          <button className="primary full" onClick={() => navigator.clipboard?.writeText(resetLink)}>Копіювати посилання</button>
        </div>}
      </div>}
    </aside>
  </div>;
}
