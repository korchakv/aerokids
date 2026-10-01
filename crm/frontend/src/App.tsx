import { useMemo, useState } from "react";

type LeadStatus = "Нова" | "Зв'язались" | "Пробне заплановано" | "Пробне пройдено" | "Очікує групу" | "Зарахований";

type Lead = {
  id: number;
  child: string;
  age: number;
  parent: string;
  phone: string;
  source: string;
  status: LeadStatus;
  comment?: string;
};

const nav = ["Дашборд", "Заявки", "Учні", "Групи", "Розклад", "Відвідування", "Оплати", "Працівники", "Локації", "Звіти"];

const initialLeads: Lead[] = [
  { id: 1, child: "Максим", age: 9, parent: "Оксана", phone: "+380 67 123 45 67", status: "Нова", source: "Сайт", comment: "Цікавиться FPV та симулятором." },
  { id: 2, child: "Артем", age: 10, parent: "Ірина", phone: "+380 50 222 14 09", status: "Пробне заплановано", source: "Instagram" },
  { id: 3, child: "Софія", age: 11, parent: "Марина", phone: "+380 96 411 28 60", status: "Очікує групу", source: "Сайт", comment: "Після пробного готова продовжувати." },
  { id: 4, child: "Данило", age: 8, parent: "Олег", phone: "+380 93 701 44 31", status: "Зв'язались", source: "Сайт" },
];

const statuses: LeadStatus[] = ["Нова", "Зв'язались", "Пробне заплановано", "Пробне пройдено", "Очікує групу", "Зарахований"];

function App() {
  const [active, setActive] = useState("Дашборд");
  const [leads, setLeads] = useState(initialLeads);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = leads.find((lead) => lead.id === selectedId) ?? null;

  const stats = useMemo(() => ({
    newLeads: leads.filter((x) => x.status === "Нова").length,
    trial: leads.filter((x) => x.status === "Пробне заплановано").length,
    waiting: leads.filter((x) => x.status === "Очікує групу").length,
  }), [leads]);

  const updateStatus = (id: number, status: LeadStatus) => {
    setLeads((items) => items.map((item) => item.id === id ? { ...item, status } : item));
  };

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="mark">✦</span><div><b>School CRM</b><small>AeroKiDS · demo tenant</small></div></div>
        <nav>{nav.map((item) => <button onClick={() => setActive(item)} className={active === item ? "active" : ""} key={item}>{item}</button>)}</nav>
        <div className="asideFooter">MVP 1 · crm-v1</div>
      </aside>

      <main>
        <header>
          <div><p className="eyebrow">Івано-Франківськ · основна локація</p><h1>{active}</h1></div>
          <div className="headerActions"><button className="search">⌕ Пошук</button><button className="primary" onClick={() => setActive("Заявки")}>+ Нова заявка</button></div>
        </header>

        {active === "Дашборд" && <>
          <section className="stats">
            <article><span>Нові заявки</span><strong>{stats.newLeads}</strong><small>потребують першого контакту</small></article>
            <article><span>Пробні заплановано</span><strong>{stats.trial}</strong><small>найближчі записи</small></article>
            <article><span>Очікують групу</span><strong>{stats.waiting}</strong><small>кандидати до формування</small></article>
            <article><span>Активні учні</span><strong>38</strong><small>у 6 групах</small></article>
          </section>
          <section className="grid">
            <article className="panel wide">
              <div className="panelHead"><div><p className="eyebrow">Потрібно опрацювати</p><h2>Останні заявки</h2></div><button className="link" onClick={() => setActive("Заявки")}>Усі заявки →</button></div>
              <LeadTable leads={leads.slice(0, 4)} onOpen={setSelectedId} />
            </article>
            <article className="panel">
              <p className="eyebrow">Сьогодні</p><h2>Пробні заняття</h2>
              <div className="timeline">
                <div><time>16:00</time><p><b>Група пробного</b><span>3 дітей · викладач Іван</span></p></div>
                <div><time>17:30</time><p><b>Група пробного</b><span>2 дітей · викладач Іван</span></p></div>
                <div><time>19:00</time><p><b>Пробне знайомство</b><span>1 дитина</span></p></div>
              </div>
            </article>
            <article className="panel">
              <p className="eyebrow">Формування груп</p><h2>Можна об'єднати</h2>
              <div className="suggestion"><strong>7 дітей</strong><span>8–10 років · початковий рівень</span><button className="primary">Переглянути кандидатів</button></div>
            </article>
          </section>
        </>}

        {active === "Заявки" && <section className="panel leadsPage">
          <div className="panelHead">
            <div><p className="eyebrow">Воронка</p><h2>Заявки та пробні</h2></div>
            <div className="filters"><button className="chip active">Усі</button><button className="chip">Нові</button><button className="chip">Пробні</button><button className="chip">Очікують групу</button></div>
          </div>
          <LeadTable leads={leads} onOpen={setSelectedId} />
        </section>}

        {active !== "Дашборд" && active !== "Заявки" && <section className="panel placeholder">
          <p className="eyebrow">Наступний модуль</p>
          <h2>{active}</h2>
          <p>Каркас модуля вже передбачений у навігації. Реалізуємо після завершення наскрізного сценарію «заявка → пробне → група → учень».</p>
        </section>}
      </main>

      {selected && <div className="drawerBackdrop" onClick={() => setSelectedId(null)}>
        <aside className="drawer" onClick={(e) => e.stopPropagation()}>
          <button className="drawerClose" onClick={() => setSelectedId(null)}>×</button>
          <p className="eyebrow">Картка заявки</p>
          <h2>{selected.child}, {selected.age} років</h2>
          <div className="contactCard"><span>Контакт</span><b>{selected.parent}</b><a href={"tel:" + selected.phone.replace(/\s/g, "")}>{selected.phone}</a></div>
          <label className="statusField">Статус
            <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value as LeadStatus)}>
              {statuses.map((status) => <option key={status}>{status}</option>)}
            </select>
          </label>
          <div className="detailGrid"><span>Джерело<b>{selected.source}</b></span><span>Вік<b>{selected.age}</b></span></div>
          {selected.comment && <div className="noteBox"><span>Коментар</span><p>{selected.comment}</p></div>}
          <div className="drawerActions">
            <button className="primary" onClick={() => updateStatus(selected.id, "Пробне заплановано")}>Записати на пробне</button>
            <button className="search" onClick={() => updateStatus(selected.id, "Очікує групу")}>Очікує групу</button>
          </div>
          <div className="history">
            <h3>Історія</h3>
            <div><i></i><p><b>Заявка створена</b><span>Джерело: {selected.source}</span></p></div>
            {selected.status !== "Нова" && <div><i></i><p><b>Статус оновлено</b><span>{selected.status}</span></p></div>}
          </div>
        </aside>
      </div>}
    </div>
  );
}

function LeadTable({ leads, onOpen }: { leads: Lead[]; onOpen: (id: number) => void }) {
  return <div className="table">
    <div className="row tableHead"><span>Дитина</span><span>Вік</span><span>Батьки</span><span>Джерело</span><span>Статус</span></div>
    {leads.map((lead) => <button className="row rowButton" key={lead.id} onClick={() => onOpen(lead.id)}>
      <b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{lead.source}</span><span className="pill">{lead.status}</span>
    </button>)}
  </div>;
}

export default App;
