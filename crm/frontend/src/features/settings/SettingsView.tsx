type SettingsViewProps = {
  organizationName: string;
  organizationTimezone: string;
  organizationCurrency: string;
  organizationLocale: string;
  organizationSaving: boolean;
  onOrganizationName: (value: string) => void;
  onOrganizationTimezone: (value: string) => void;
  onOrganizationCurrency: (value: string) => void;
  onOrganizationLocale: (value: string) => void;
  onSaveOrganization: () => void;
  theme: "light" | "dark";
  onTheme: (theme: "light" | "dark") => void;
  uiScale: number;
  canScaleDown: boolean;
  canScaleUp: boolean;
  onScaleDown: () => void;
  onScaleUp: () => void;
  organizationSlug: string;
  roleName: string;
};

export function SettingsView({
  organizationName,
  organizationTimezone,
  organizationCurrency,
  organizationLocale,
  organizationSaving,
  onOrganizationName,
  onOrganizationTimezone,
  onOrganizationCurrency,
  onOrganizationLocale,
  onSaveOrganization,
  theme,
  onTheme,
  uiScale,
  canScaleDown,
  canScaleUp,
  onScaleDown,
  onScaleUp,
  organizationSlug,
  roleName,
}: SettingsViewProps) {
  return <section className="settingsLayout">
    <div className="settingsPrimaryColumn">
      <article className="panel settingsPanel">
        <div className="panelHead"><div><p className="eyebrow">Організація</p><h2>Основні налаштування</h2></div></div>
        <p className="settingsIntro">Ці значення належать конкретній школі або гуртку й не впливають на інші організації в CRM.</p>
        <label>Назва організації<input value={organizationName} onChange={(event) => onOrganizationName(event.target.value)} /></label>
        <div className="formTwo">
          <label>Часовий пояс<input value={organizationTimezone} onChange={(event) => onOrganizationTimezone(event.target.value)} placeholder="Europe/Kyiv" /></label>
          <label>Валюта<input value={organizationCurrency} maxLength={3} onChange={(event) => onOrganizationCurrency(event.target.value.toUpperCase())} placeholder="UAH" /></label>
        </div>
        <label>Локаль<input value={organizationLocale} onChange={(event) => onOrganizationLocale(event.target.value)} placeholder="uk-UA" /></label>
        <button className="primary" disabled={organizationSaving || !organizationName.trim()} onClick={onSaveOrganization}>{organizationSaving ? "Зберігаємо…" : "Зберегти налаштування"}</button>
      </article>

      <article className="panel settingsPanel appearanceSettings">
        <div className="panelHead"><div><p className="eyebrow">Інтерфейс</p><h2>Вигляд інтерфейсу</h2></div></div>
        <p className="settingsIntro">Тема та масштаб зберігаються для цього браузера. Це зручно, якщо потрібно зробити CRM контрастнішою або збільшити всі елементи для кращої читабельності.</p>
        <div className="appearanceSettingRow">
          <div><b>Тема</b><small>Світла або темна схема</small></div>
          <div className="appearanceThemeSwitch" role="group" aria-label="Тема інтерфейсу">
            <button type="button" className={theme === "light" ? "active" : ""} onClick={() => onTheme("light")}>Світла</button>
            <button type="button" className={theme === "dark" ? "active" : ""} onClick={() => onTheme("dark")}>Темна</button>
          </div>
        </div>
        <div className="appearanceSettingRow">
          <div><b>Масштаб</b><small>Пропорційно збільшує текст, кнопки, поля та відступи</small></div>
          <div className="uiScaleControl settingsScaleControl" aria-label="Масштаб інтерфейсу">
            <button type="button" aria-label="Зменшити масштаб" title="Зменшити" disabled={!canScaleDown} onClick={onScaleDown}>A−</button>
            <span><b>{Math.round(uiScale * 100)}%</b><small>масштаб</small></span>
            <button type="button" aria-label="Збільшити масштаб" title="Збільшити" disabled={!canScaleUp} onClick={onScaleUp}>A+</button>
          </div>
        </div>
      </article>
    </div>
    <aside className="panel settingsHelp">
      <p className="eyebrow">SaaS</p><h2>Налаштування tenant</h2>
      <p>Часовий пояс використовується для дат і розкладу, валюта — для фінансів, локаль — для форматування чисел та дат.</p>
      <div className="summaryMetric"><span>Slug</span><strong>{organizationSlug || "—"}</strong></div>
      <div className="summaryMetric"><span>Ваша роль</span><strong>{roleName}</strong></div>
    </aside>
  </section>;
}
