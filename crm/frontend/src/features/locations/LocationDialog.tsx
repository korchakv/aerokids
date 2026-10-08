import type { EntityId } from "../leads/model";

type MaybePromise = void | Promise<void>;

export type LocationDialogProps = {
  open: boolean;
  locationEditId: EntityId | null;
  locationName: string;
  locationAddress: string;
  locationSaving: boolean;
  locationDeleteSaving: boolean;
  locationReturnToGroup: boolean;
  onClose: () => void;
  onNameChange: (value: string) => void;
  onAddressChange: (value: string) => void;
  onSave: () => MaybePromise;
  onDelete: () => MaybePromise;
};

export function LocationDialog({
  open,
  locationEditId,
  locationName,
  locationAddress,
  locationSaving,
  locationDeleteSaving,
  locationReturnToGroup,
  onClose,
  onNameChange,
  onAddressChange,
  onSave,
  onDelete,
}: LocationDialogProps) {
  if (!open) return null;
  return <div className="modalBackdrop">
    <div className="groupModal locationEditModal" data-testid="location-dialog" onClick={(event) => event.stopPropagation()}>
      <button className="drawerClose" aria-label="Закрити локацію" onClick={onClose}>×</button>
      <p className="eyebrow">Мережа</p><h2>{locationEditId ? "Редагувати локацію" : "Нова локація"}</h2>
      {locationReturnToGroup && <p className="modalIntro">Після збереження повернемо вас до створення групи й виберемо нову локацію автоматично.</p>}
      <label>Назва<input autoFocus value={locationName} onChange={(event) => onNameChange(event.target.value)} placeholder="AeroKids Центр" /></label>
      <label>Адреса<input value={locationAddress} onChange={(event) => onAddressChange(event.target.value)} placeholder="Івано-Франківськ" /></label>
      <button className="primary full" disabled={!locationName.trim() || locationSaving || locationDeleteSaving} onClick={() => void onSave()}>{locationSaving ? "Зберігаємо…" : locationEditId ? "Зберегти зміни" : "Створити локацію"}</button>
      {locationEditId && <div className="subtleDeleteRow"><button className="subtleDangerAction" type="button" disabled={locationSaving || locationDeleteSaving} onClick={() => void onDelete()}>{locationDeleteSaving ? "Видаляємо…" : "Видалити локацію"}</button></div>}
    </div>
  </div>;
}
