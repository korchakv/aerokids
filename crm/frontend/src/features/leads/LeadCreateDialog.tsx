import type { Dispatch, SetStateAction } from "react";
import type { IntakeDuplicateMatch } from "../../api";
import { crmStatusLabel } from "../workspace/adapters";
import { emailError, formatUaPhone, normalizeUaPhone, personNameError, uaPhoneError } from "../../utils/contact";

type Setter<T> = Dispatch<SetStateAction<T>>;
type MaybePromise = void | Promise<void>;

export type LeadCreateDialogProps = {
  open: boolean;
  leadChildName: string;
  leadChildLastName: string;
  leadChildPhone: string;
  leadAge: number;
  leadContactName: string;
  leadPhone: string;
  leadSource: string;
  leadComment: string;
  duplicateChecking: boolean;
  duplicateMatches: IntakeDuplicateMatch[];
  setLeadChildName: Setter<string>;
  setLeadChildLastName: Setter<string>;
  setLeadChildPhone: Setter<string>;
  setLeadAge: Setter<number>;
  setLeadContactName: Setter<string>;
  setLeadPhone: Setter<string>;
  setLeadSource: Setter<string>;
  setLeadComment: Setter<string>;
  onClose: () => void;
  onCheckDuplicates: () => void | Promise<IntakeDuplicateMatch[]>;
  onOpenDuplicate: (match: IntakeDuplicateMatch) => void;
  onCreate: () => MaybePromise;
};

export function LeadCreateDialog({
  open,
  leadChildName,
  leadChildLastName,
  leadChildPhone,
  leadAge,
  leadContactName,
  leadPhone,
  leadSource,
  leadComment,
  duplicateChecking,
  duplicateMatches,
  setLeadChildName,
  setLeadChildLastName,
  setLeadChildPhone,
  setLeadAge,
  setLeadContactName,
  setLeadPhone,
  setLeadSource,
  setLeadComment,
  onClose,
  onCheckDuplicates,
  onOpenDuplicate,
  onCreate,
}: LeadCreateDialogProps) {
  if (!open) return null;
  const likelyDuplicate = duplicateMatches.some((item) => item.likely_same_student);
  const invalid = Boolean(
    personNameError(leadChildName, "Ім’я дитини")
    || (leadChildLastName.trim() ? personNameError(leadChildLastName, "Прізвище дитини") : "")
    || uaPhoneError(leadChildPhone, false)
    || personNameError(leadContactName, "Відповідальна особа")
    || uaPhoneError(leadPhone)
  );

  return <div className="modalBackdrop">
    <div className="groupModal leadCreateModal" data-testid="lead-create-dialog" onClick={(event) => event.stopPropagation()}>
      <button className="drawerClose" aria-label="Закрити нову заявку" onClick={onClose}>×</button>
      <p className="eyebrow">Нова заявка</p><h2>Додати дитину</h2>
      <div className="formTwo leadCreatePair">
        <label>Ім’я дитини *<input className={leadChildName && personNameError(leadChildName, "Ім’я дитини") ? "inputInvalid" : ""} value={leadChildName} maxLength={120} onChange={(event) => setLeadChildName(event.target.value)} placeholder="Максим" />{leadChildName && personNameError(leadChildName, "Ім’я дитини") && <small className="fieldError">{personNameError(leadChildName, "Ім’я дитини")}</small>}</label>
        <label>Прізвище дитини<input className={leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") ? "inputInvalid" : ""} value={leadChildLastName} maxLength={120} onChange={(event) => setLeadChildLastName(event.target.value)} placeholder="Коваль" /><small className="leadFormHint">Необов’язково · можна дописати пізніше</small>{leadChildLastName && personNameError(leadChildLastName, "Прізвище дитини") && <small className="fieldError">{personNameError(leadChildLastName, "Прізвище дитини")}</small>}</label>
      </div>
      <div className="formTwo leadCreatePair">
        <label>Вік<input type="number" min={3} max={25} value={leadAge} onChange={(event) => setLeadAge(Number(event.target.value))} /></label>
        <label>Телефон дитини<input type="tel" inputMode="tel" maxLength={19} className={leadChildPhone && uaPhoneError(leadChildPhone, false) ? "inputInvalid" : ""} value={leadChildPhone} onChange={(event) => setLeadChildPhone(event.target.value)} onBlur={() => { if (normalizeUaPhone(leadChildPhone)) setLeadChildPhone(formatUaPhone(leadChildPhone)); void onCheckDuplicates(); }} placeholder="+380 67 123 45 67" /><small className="leadFormHint">Необов’язково</small>{leadChildPhone && uaPhoneError(leadChildPhone, false) && <small className="fieldError">{uaPhoneError(leadChildPhone, false)}</small>}</label>
      </div>
      <label>Ім’я відповідальної особи *<input className={leadContactName && personNameError(leadContactName, "Відповідальна особа") ? "inputInvalid" : ""} value={leadContactName} maxLength={160} autoComplete="name" onChange={(event) => setLeadContactName(event.target.value)} placeholder="Оксана або Оксана Петренко" /><small className="leadFormHint">Прізвище можна дописати пізніше</small>{leadContactName && personNameError(leadContactName, "Відповідальна особа") && <small className="fieldError">{personNameError(leadContactName, "Відповідальна особа")}</small>}</label>
      <label>Телефон відповідального *<input type="tel" inputMode="tel" autoComplete="tel" maxLength={19} className={leadPhone && uaPhoneError(leadPhone) ? "inputInvalid" : ""} value={leadPhone} onChange={(event) => setLeadPhone(event.target.value)} onBlur={() => { if (normalizeUaPhone(leadPhone)) setLeadPhone(formatUaPhone(leadPhone)); void onCheckDuplicates(); }} placeholder="+380 67 123 45 67" />{leadPhone && uaPhoneError(leadPhone) && <small className="fieldError">{uaPhoneError(leadPhone)}</small>}</label>
      {duplicateChecking && <div className="duplicateCheck pending"><span className="syncPulse" />Перевіряємо номер у CRM…</div>}
      {!duplicateChecking && duplicateMatches.length > 0 && <div className={"duplicateCheck " + (likelyDuplicate ? "blocked" : "warning")}>
        <b>{likelyDuplicate ? "Такий номер уже зареєстровано" : "Цей номер уже є в CRM"}</b>
        <small>{likelyDuplicate ? "Схоже, це вже існуюча дитина. Перевірте картку, щоб не створювати дубль." : "Можливо, це інша дитина з тієї самої сім’ї. Створення дозволено, але перевірте збіг."}</small>
        <div className="duplicateMatches">{duplicateMatches.slice(0, 4).map((match) => <button type="button" className="duplicateMatch" key={match.student_id} onClick={() => onOpenDuplicate(match)}>
          <span><b>{match.first_name} {match.last_name ?? ""}</b><small>{match.age ?? "—"} років · {crmStatusLabel(match.crm_status)}</small><small>{match.contact_name ?? "Контакт не вказано"}{match.contact_phone ? " · " + formatUaPhone(match.contact_phone) : ""}</small></span>
          <strong>Перейти та перевірити →</strong>
        </button>)}</div>
      </div>}
      <label>Джерело<select value={leadSource} onChange={(event) => setLeadSource(event.target.value)}>
        <option value="phone">Телефон</option>
        <option value="website">Сайт</option>
        <option value="instagram">Instagram</option>
        <option value="recommendation">Рекомендація</option>
        <option value="walk-in">Зайшли особисто</option>
      </select></label>
      <label>Коментар<textarea value={leadComment} onChange={(event) => setLeadComment(event.target.value)} placeholder="Що цікавить, бажаний час, примітки…" /></label>
      <button className="primary full" disabled={duplicateChecking || likelyDuplicate || invalid} onClick={() => void onCreate()}>{duplicateChecking ? "Перевіряємо номер…" : likelyDuplicate ? "Перевірте існуючу картку" : "Створити заявку"}</button>
    </div>
  </div>;
}
