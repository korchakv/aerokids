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
  trialAt?: string;
  trialLocation?: string;
  trialResult?: "scheduled" | "completed" | "no_show";
  recommendedLevel?: string;
  teacherNotes?: string;
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
  const [trialMode, setTrialMode] = useState<"schedule" | "complete" | null>(null);
  const [trialAt, setTrialAt] = useState("2026-10-05T17:00");
  const [trialLocation, setTrialLocation] = useState("Основна локація");
  const [recommendedLevel, setRecommendedLevel] = useState("Початковий");
  const [teacherNotes, setTeacherNotes] = useState("");
  const selected = leads.find((lead) => lead.id === selectedId) ?? null;

  const stats = useMemo(() => ({
    newLeads: leads.filter((x) => x.status === "Нова").length,
    trial: leads.filter((x) => x.status === "Пробне заплановано").length,
    waiting: leads.filter((x) => x.status === "Очікує групу").length,
  }), [leads]);

  const updateStatus = (id: number, status: LeadStatus) => {
    setLeads((items) => items.map((item) => item.id === id ? { ...item, status } : item));
  };

  const scheduleTrial = () => {
    if (!selected) return;
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: "Пробне заплановано",
      trialAt,
      trialLocation,
      trialResult: "scheduled",
    } : item));
    setTrialMode(null);
  };

  const completeTrial = (result: "completed" | "no_show") => {
    if (!selected) return;
    setLeads((items) => items.map((item) => item.id === selected.id ? {
      ...item,
      status: result === "completed" ? "Очікує групу" : "Зв'язались",
      trialResult: result,
      recommendedLevel: result === "completed" ? recommendedLevel : item.recommendedLevel,
      teacherNotes: teacherNotes || item.teacherNotes,
    } : item));
    setTrialMode(null);
  };

  const openLead = (id: number) => {
    setSelectedId(id);
    setTrialMode(null);
    const lead = leads.find((item) => item.id === id);
    if (lead?.trialAt) setTrialAt(lead.trialAt);
    if (lead?.trialLocation) setTrialLocation(lead.trialLocation);
    if (lead?.recommendedLevel) setRecommendedLevel(lead.recommendedLevel);
    setTeacherNotes(lead?.teacherNotes ?? "");
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
              <LeadTable leads={leads.slice(0, 4)} onOpen={openLead} />
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
          <LeadTable leads={leads} onOpen={openLead} />
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
          {selected.trialAt && <div className="trialSummary">
            <span>Пробне заняття</span>
            <b>{new Date(selected.trialAt).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</b>
            <small>{selected.trialLocation ?? "Локацію не вказано"}</small>
          </div>}

          <div className="drawerActions">
            <button className="primary" onClick={() => setTrialMode("schedule")}>{selected.trialAt ? "Змінити пробне" : "Записати на пробне"}</button>
            {selected.trialAt && selected.trialResult !== "completed" && <button className="search" onClick={() => setTrialMode("complete")}>Результат пробного</button>}
          </div>

          {trialMode === "schedule" && <div className="workflowBox">
            <div className="workflowHead"><h3>Запис на пробне</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <label>Дата і час<input type="datetime-local" value={trialAt} onChange={(e) => setTrialAt(e.target.value)} /></label>
            <label>Локація<select value={trialLocation} onChange={(e) => setTrialLocation(e.target.value)}>
              <option>Основна локація</option>
              <option>Локація 2</option>
            </select></label>
            <button className="primary full" onClick={scheduleTrial}>Підтвердити пробне</button>
          </div>}

          {trialMode === "complete" && <div className="workflowBox">
            <div className="workflowHead"><h3>Результат пробного</h3><button onClick={() => setTrialMode(null)}>×</button></div>
            <label>Рекомендований рівень<select value={recommendedLevel} onChange={(e) => setRecommendedLevel(e.target.value)}>
              <option>Початковий</option>
              <option>Середній</option>
              <option>Просунутий</option>
            </select></label>
            <label>Коментар викладача<textarea value={teacherNotes} onChange={(e) => setTeacherNotes(e.target.value)} placeholder="Що сподобалось, як дитина справилась, що рекомендуємо" /></label>
            <div className="resultActions"><button className="primary" onClick={() => completeTrial("completed")}>Пробне пройдено</button><button className="search" onClick={() => completeTrial("no_show")}>Не прийшов</button></div>
          </div>}

          {selected.trialResult === "completed" && <div className="resultCard">
            <span>Пробне завершено</span>
            <b>{selected.recommendedLevel ?? "Рівень не вказано"}</b>
            {selected.teacherNotes && <p>{selected.teacherNotes}</p>}
            <small>Дитина автоматично перейшла в «Очікує групу».</small>
          </div>}

          <div className="history">
            <h3>Історія</h3>
            <div><i></i><p><b>Заявка створена</b><span>Джерело: {selected.source}</span></p></div>
            {selected.trialAt && <div><i></i><p><b>Пробне заплановано</b><span>{new Date(selected.trialAt).toLocaleString("uk-UA")}</span></p></div>}
            {selected.trialResult === "completed" && <div><i></i><p><b>Пробне пройдено</b><span>Рівень: {selected.recommendedLevel ?? "не вказано"}</span></p></div>}
            {selected.trialResult === "no_show" && <div><i></i><p><b>Не прийшов на пробне</b><span>Потрібен повторний контакт</span></p></div>}
            {selected.status !== "Нова" && <div><i></i><p><b>Поточний статус</b><span>{selected.status}</span></p></div>}
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
