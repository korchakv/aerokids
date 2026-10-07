import { UiIcon } from "../../components/UiIcon";
import type { GroupItem } from "../groups/types";
import type { EntityId } from "../leads/model";
import type { StaffDemo } from "../staff/model";
import type { LocationDemo } from "./types";

type LocationsViewProps = {
  locations: LocationDemo[];
  staff: StaffDemo[];
  groups: GroupItem[];
  canManageLocations: boolean;
  onCreate: () => void;
  onEdit: (location: LocationDemo) => void;
};

export function LocationsView({
  locations,
  staff,
  groups,
  canManageLocations,
  onCreate,
  onEdit,
}: LocationsViewProps) {
  const groupLocation = (group: GroupItem): string | undefined => group.location;
  const staffAtLocation = (locationId: EntityId) =>
    staff.filter((member) => member.locationIds.includes(locationId) && member.isActive);

  return <section className="locationsLayout">
    <div className="panelHead locationsHead">
      <div><p className="eyebrow">Мережа</p><h2>Локації школи</h2></div>
      {canManageLocations && <button className="primary" onClick={onCreate}>+ Додати локацію</button>}
    </div>
    <div className="locationCards">
      {locations.map((location) => {
        const locationStaff = staffAtLocation(location.id);
        const locationGroups = groups.filter((group) => groupLocation(group) === location.name);
        return <article className="panel locationCard" key={location.id}>
          <div className="locationTop">
            <span className="locationIcon">⌂</span>
            <div className="locationTopActions">
              <span className={"staffStatus " + (location.isActive ? "active" : "inactive")}>{location.isActive ? "Активна" : "Неактивна"}</span>
              {canManageLocations && <button
                className="locationEditIcon"
                type="button"
                aria-label={"Редагувати " + location.name}
                title="Редагувати локацію"
                onClick={() => onEdit(location)}
              ><UiIcon name="edit" size={14} /></button>}
            </div>
          </div>
          <h2>{location.name}</h2>
          <p>{location.address || "Адресу ще не вказано"}</p>
          <div className="locationMetrics">
            <span><b>{locationStaff.length}</b> працівників</span>
            <span><b>{locationGroups.length}</b> груп</span>
          </div>
          <div className="locationPeople">
            {locationStaff.slice(0, 4).map((member) => <i title={member.fullName} key={member.id}>{member.fullName[0]}</i>)}
          </div>
        </article>;
      })}
    </div>
  </section>;
}
