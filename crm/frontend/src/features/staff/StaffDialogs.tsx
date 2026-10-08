import type { Dispatch, SetStateAction } from "react";
import { emailError, formatUaPhone, normalizeUaPhone, personNameError, uaPhoneError } from "../../utils/contact";
import type { StaffRoleDemo } from "./model";

type Setter<T> = Dispatch<SetStateAction<T>>;
type MaybePromise = void | Promise<void>;

export type StaffDialogsProps = {
  showInviteForm: boolean;
  inviteEmail: string;
  inviteRole: StaffRoleDemo;
  inviteCanTeach: boolean;
  inviteLink: string;
  setShowInviteForm: Setter<boolean>;
  setInviteEmail: Setter<string>;
  setInviteRole: Setter<StaffRoleDemo>;
  setInviteCanTeach: Setter<boolean>;
  onCreateInvitation: () => MaybePromise;

  showStaffForm: boolean;
  staffName: string;
  staffRole: StaffRoleDemo;
  staffCanTeach: boolean;
  staffEmail: string;
  staffPhone: string;
  setShowStaffForm: Setter<boolean>;
  setStaffName: Setter<string>;
  setStaffRole: Setter<StaffRoleDemo>;
  setStaffCanTeach: Setter<boolean>;
  setStaffEmail: Setter<string>;
  setStaffPhone: Setter<string>;
  onCreateStaff: () => MaybePromise;
};

export function StaffDialogs(props: StaffDialogsProps) {
  const {
    showInviteForm,
    inviteEmail,
    inviteRole,
    inviteCanTeach,
    inviteLink,
    setShowInviteForm,
    setInviteEmail,
    setInviteRole,
    setInviteCanTeach,
    onCreateInvitation,
    showStaffForm,
    staffName,
    staffRole,
    staffCanTeach,
    staffEmail,
    staffPhone,
    setShowStaffForm,
    setStaffName,
    setStaffRole,
    setStaffCanTeach,
    setStaffEmail,
    setStaffPhone,
    onCreateStaff,
  } = props;

  return <>
    {showInviteForm && <div className="modalBackdrop">
      <div className="groupModal" data-testid="invite-dialog" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" aria-label="Закрити запрошення" onClick={() => setShowInviteForm(false)}>×</button>
        <p className="eyebrow">Доступ до CRM</p><h2>Запросити працівника</h2>
        {!inviteLink ? <>
          <label>Email *<input type="email" autoComplete="email" maxLength={255} className={inviteEmail && emailError(inviteEmail, true) ? "inputInvalid" : ""} value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="teacher@example.com" />{inviteEmail && emailError(inviteEmail, true) && <small className="fieldError">{emailError(inviteEmail, true)}</small>}</label>
          <label>Роль<select value={inviteRole} onChange={(event) => { const role = event.target.value as StaffRoleDemo; setInviteRole(role); if (role === "Викладач") setInviteCanTeach(true); }}>{["Адміністратор", "Менеджер", "Викладач", "Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
          <label className="toggleRow responsibilityToggle"><input type="checkbox" checked={inviteCanTeach || inviteRole === "Викладач"} disabled={inviteRole === "Викладач"} onChange={(event) => setInviteCanTeach(event.target.checked)} /><span><b>Може викладати</b><small>Дозволяє призначати цього працівника викладачем груп незалежно від його ролі в CRM.</small></span></label>
          <button className="primary full" disabled={Boolean(emailError(inviteEmail, true))} onClick={() => void onCreateInvitation()}>Створити запрошення</button>
        </> : <>
          <div className="inviteSuccess"><b>Запрошення готове</b><p>Надішліть це посилання працівнику. Воно одноразове та діє 7 днів.</p><code>{inviteLink}</code></div>
          <button className="primary full" onClick={() => navigator.clipboard?.writeText(inviteLink)}>Копіювати посилання</button>
        </>}
      </div>
    </div>}

    {showStaffForm && <div className="modalBackdrop">
      <div className="groupModal" data-testid="staff-create-dialog" onClick={(event) => event.stopPropagation()}>
        <button className="drawerClose" aria-label="Закрити нового працівника" onClick={() => setShowStaffForm(false)}>×</button>
        <p className="eyebrow">Команда</p><h2>Новий працівник</h2>
        <label>Ім’я та прізвище *<input autoComplete="name" maxLength={160} className={staffName && personNameError(staffName, "Ім’я та прізвище") ? "inputInvalid" : ""} value={staffName} onChange={(event) => setStaffName(event.target.value)} placeholder="Іван Петренко" />{staffName && personNameError(staffName, "Ім’я та прізвище") && <small className="fieldError">{personNameError(staffName, "Ім’я та прізвище")}</small>}</label>
        <label>Роль<select value={staffRole} onChange={(event) => { const role = event.target.value as StaffRoleDemo; setStaffRole(role); if (role === "Викладач") setStaffCanTeach(true); }}>{["Власник", "Адміністратор", "Менеджер", "Викладач", "Бухгалтер"].map((role) => <option key={role}>{role}</option>)}</select></label>
        <label className="toggleRow responsibilityToggle"><input type="checkbox" checked={staffCanTeach || staffRole === "Викладач"} disabled={staffRole === "Викладач"} onChange={(event) => setStaffCanTeach(event.target.checked)} /><span><b>Може викладати</b><small>Працівника можна буде призначати викладачем груп.</small></span></label>
        <div className="formTwo">
          <label>Email<input type="email" autoComplete="email" maxLength={255} className={staffEmail && emailError(staffEmail) ? "inputInvalid" : ""} value={staffEmail} onChange={(event) => setStaffEmail(event.target.value)} />{staffEmail && emailError(staffEmail) && <small className="fieldError">{emailError(staffEmail)}</small>}</label>
          <label>Телефон<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={staffPhone && uaPhoneError(staffPhone, false) ? "inputInvalid" : ""} value={staffPhone} onChange={(event) => setStaffPhone(event.target.value)} onBlur={() => { if (normalizeUaPhone(staffPhone)) setStaffPhone(formatUaPhone(staffPhone)); }} placeholder="+380 67 123 45 67" />{staffPhone && uaPhoneError(staffPhone, false) && <small className="fieldError">{uaPhoneError(staffPhone, false)}</small>}</label>
        </div>
        <div className="formNotice">Для працівника потрібно вказати хоча б email або телефон.</div>
        <button className="primary full" disabled={Boolean(personNameError(staffName, "Ім’я та прізвище") || emailError(staffEmail) || uaPhoneError(staffPhone, false) || (!staffEmail.trim() && !staffPhone.trim()))} onClick={() => void onCreateStaff()}>Додати працівника</button>
      </div>
    </div>}
  </>;
}
