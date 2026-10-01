const nav = ["Дашборд", "Заявки", "Учні", "Групи", "Розклад", "Відвідування", "Оплати", "Працівники", "Локації", "Звіти"];

const leads = [
  { child: "Максим", age: 9, parent: "Оксана", status: "Нова", source: "Сайт" },
  { child: "Артем", age: 10, parent: "Ірина", status: "Пробне 03.10", source: "Instagram" },
  { child: "Софія", age: 11, parent: "Марина", status: "Очікує групу", source: "Сайт" },
];

function App() {
  return (
    <div className="shell">
      <aside>
        <div className="brand"><span className="mark">✦</span><div><b>School CRM</b><small>AeroKiDS · demo tenant</small></div></div>
        <nav>{nav.map((item, i) => <button className={i === 0 ? "active" : ""} key={item}>{item}</button>)}</nav>
        <div className="asideFooter">MVP 1 · crm-v1</div>
      </aside>
      <main>
        <header>
          <div><p className="eyebrow">Івано-Франківськ · основна локація</p><h1>Дашборд</h1></div>
          <div className="headerActions"><button className="search">⌕ Пошук</button><button className="primary">+ Нова заявка</button></div>
        </header>

        <section className="stats">
          <article><span>Нові заявки</span><strong>4</strong><small>2 потребують відповіді</small></article>
          <article><span>Пробні сьогодні</span><strong>6</strong><small>на 3 часові слоти</small></article>
          <article><span>Очікують групу</span><strong>9</strong><small>можна формувати 1 групу</small></article>
          <article><span>Активні учні</span><strong>38</strong><small>у 6 групах</small></article>
        </section>

        <section className="grid">
          <article className="panel wide">
            <div className="panelHead"><div><p className="eyebrow">Потрібно опрацювати</p><h2>Останні заявки</h2></div><button className="link">Усі заявки →</button></div>
            <div className="table">
              <div className="row tableHead"><span>Дитина</span><span>Вік</span><span>Батьки</span><span>Джерело</span><span>Статус</span></div>
              {leads.map((lead) => <div className="row" key={lead.child}><b>{lead.child}</b><span>{lead.age}</span><span>{lead.parent}</span><span>{lead.source}</span><span className="pill">{lead.status}</span></div>)}
            </div>
          </article>

          <article className="panel">
            <p className="eyebrow">Сьогодні</p><h2>Пробні заняття</h2>
            <div className="timeline">
              <div><time>16:00</time><p><b>Група пробного</b><span>3 дітей · викладач Іван</span></p></div>
              <div><time>17:30</time><p><b>Група пробного</b><span>2 дітей · викладач Іван</span></p></div>
              <div><time>19:00</time><p><b>Індивідуальне знайомство</b><span>1 дитина</span></p></div>
            </div>
          </article>

          <article className="panel">
            <p className="eyebrow">Формування груп</p><h2>Можна об'єднати</h2>
            <div className="suggestion"><strong>7 дітей</strong><span>8–10 років · початковий рівень</span><button className="primary">Переглянути кандидатів</button></div>
          </article>
        </section>
      </main>
    </div>
  );
}

export default App;
