import { UiIcon } from "../../components/UiIcon";
import type { PaymentDemo, PlanDemo } from "../billing/model";
import type { GroupItem } from "../groups/types";
import type { EntityId, Lead } from "../leads/model";
import type { StaffDemo } from "../staff/model";
import { formatUaPhone } from "../../utils/contact";

type GlobalSearchProps = {
  open: boolean;
  query: string;
  searchTerm: string;
  searchLeads: Lead[];
  searchGroups: GroupItem[];
  searchStaff: StaffDemo[];
  searchPayments: PaymentDemo[];
  leads: Lead[];
  plans: PlanDemo[];
  money: (value: number) => string;
  onOpenChange: (open: boolean) => void;
  onQueryChange: (query: string) => void;
  onOpenLead: (id: EntityId) => void;
  onOpenStudent: (id: EntityId) => void;
  onOpenGroup: (id: EntityId) => void;
  onOpenPayment: (id: EntityId) => void;
  onOpenStaff: (id: EntityId) => void;
};

export function GlobalSearch({
  open,
  query,
  searchTerm,
  searchLeads,
  searchGroups,
  searchStaff,
  searchPayments,
  leads,
  plans,
  money,
  onOpenChange,
  onQueryChange,
  onOpenLead,
  onOpenStudent,
  onOpenGroup,
  onOpenPayment,
  onOpenStaff,
}: GlobalSearchProps) {
  const close = () => {
    onOpenChange(false);
    onQueryChange("");
  };

  return <div
    className={"globalSearchShell " + (open ? "open" : "")}
    onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
        onOpenChange(false);
      }
    }}
  >
    {open ? <>
      <div className="globalSearchBar">
        <span aria-hidden="true"><UiIcon name="search" size={16} /></span>
        <input
          autoFocus
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Пошук у CRM…"
          aria-label="Глобальний пошук"
        />
        <button type="button" aria-label="Закрити пошук" title="Закрити пошук" onClick={close}><UiIcon name="x" size={16} /></button>
      </div>
      <div className="globalSearchDropdown">
        {!searchTerm && <div className="searchHint compact">Ім’я, прізвище, телефон, відповідальний, група…</div>}
        {searchTerm && searchLeads.length + searchGroups.length + searchStaff.length + searchPayments.length === 0 && <div className="searchHint compact">Нічого не знайдено.</div>}
        {searchLeads.length > 0 && <div className="searchResults compactResults">
          <h3>Діти та заявки</h3>
          {searchLeads.map((item) => <button key={item.id} onClick={() => { close(); item.status === "Зарахований" ? onOpenStudent(item.id) : onOpenLead(item.id); }}>
            <span><b>{item.child}</b><small>{item.age} років · {item.parent}{item.phone ? " · " + formatUaPhone(item.phone) : ""}{item.childPhone ? " · дитина " + formatUaPhone(item.childPhone) : ""}</small></span>
            <i>{item.status}</i>
          </button>)}
        </div>}
        {searchGroups.length > 0 && <div className="searchResults compactResults">
          <h3>Групи</h3>
          {searchGroups.map((item) => <button key={item.id} onClick={() => { close(); onOpenGroup(item.id); }}>
            <span><b>{item.name}</b><small>{item.ages} · {item.location}{item.teacherName ? " · " + item.teacherName : ""}</small></span>
            <i>{item.members.length}/{item.capacity}</i>
          </button>)}
        </div>}
        {searchPayments.length > 0 && <div className="searchResults compactResults">
          <h3>Оплати</h3>
          {searchPayments.map((payment) => {
            const student = leads.find((lead) => lead.id === payment.studentId);
            const plan = plans.find((item) => item.id === payment.planId);
            return <button key={payment.id} onClick={() => { close(); onOpenPayment(payment.id); }}>
              <span><b>{student?.child ?? "Учень"} · {plan?.name ?? "Оплата"}</b><small>{student?.parent ?? "Відповідальний не вказаний"}{student?.phone ? " · " + formatUaPhone(student.phone) : ""}</small></span>
              <i>{payment.balanceAmount > 0 ? "Залишок " + money(payment.balanceAmount) : "Сплачено"}</i>
            </button>;
          })}
        </div>}
        {searchStaff.length > 0 && <div className="searchResults compactResults">
          <h3>Працівники</h3>
          {searchStaff.map((item) => <button key={item.id} onClick={() => { close(); onOpenStaff(item.id); }}>
            <span><b>{item.fullName}</b><small>{item.role} · {item.email || item.phone}</small></span>
            <i>{item.isActive ? "Активний" : "Неактивний"}</i>
          </button>)}
        </div>}
      </div>
    </> : <button className="search globalSearchTrigger" aria-label="Пошук" title="Пошук" onClick={() => { onQueryChange(""); onOpenChange(true); }}><UiIcon name="search" size={17} /><span>Пошук</span></button>}
  </div>;
}
