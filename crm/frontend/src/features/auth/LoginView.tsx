import { useEffect, useState } from "react";
import { acceptInvite, bootstrapOwner, getBootstrapStatus, getInvitationStatus, login, resetPassword, type Session } from "../../api";
import { UiIcon } from "../../components/UiIcon";

export function LoginView({ onAuthenticated, theme, onToggleTheme }: { onAuthenticated: (session: Session) => void; theme: "dark" | "light"; onToggleTheme: () => void }) {
  const params = new URLSearchParams(window.location.search);
  const inviteToken = params.get("invite");
  const resetToken = params.get("reset");
  const [inviteName, setInviteName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false);
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [organizationName, setOrganizationName] = useState("AeroKids");
  const [organizationSlug, setOrganizationSlug] = useState("aerokids");
  const [ownerName, setOwnerName] = useState("");
  const [bootstrapSecret, setBootstrapSecret] = useState("");
  const [inviteStatus, setInviteStatus] = useState<"checking" | "valid" | "accepted" | "expired" | "invalid" | "error">(inviteToken ? "checking" : "valid");

  useEffect(() => {
    document.body.classList.add("crmLoginActive");
    return () => document.body.classList.remove("crmLoginActive");
  }, []);

  useEffect(() => {
    if (inviteToken) {
      setCheckingBootstrap(false);
      setInviteStatus("checking");
      getInvitationStatus(inviteToken)
        .then((status) => setInviteStatus(status))
        .catch(() => setInviteStatus("error"));
      return;
    }
    if (resetToken) {
      setCheckingBootstrap(false);
      return;
    }
    getBootstrapStatus()
      .then(setBootstrapAvailable)
      .catch(() => setBootstrapAvailable(false))
      .finally(() => setCheckingBootstrap(false));
  }, [inviteToken, resetToken]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onAuthenticated(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося увійти");
    } finally {
      setLoading(false);
    }
  };

  const acceptInvitation = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!inviteToken) return;
    setError("");
    setLoading(true);
    try {
      const nextSession = await acceptInvite({
        invite_token: inviteToken,
        full_name: inviteName.trim(),
        password,
      });
      window.history.replaceState({}, "", window.location.pathname);
      onAuthenticated(nextSession);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не вдалося прийняти запрошення";
      if (message.includes("already been accepted")) {
        setInviteStatus("accepted");
        setError("");
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const completePasswordReset = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!resetToken) return;
    setError("");
    setLoading(true);
    try {
      const nextSession = await resetPassword({
        reset_token: resetToken,
        password,
      });
      window.history.replaceState({}, "", window.location.pathname);
      onAuthenticated(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося змінити пароль");
    } finally {
      setLoading(false);
    }
  };

  const setup = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      onAuthenticated(await bootstrapOwner({
        organization_name: organizationName.trim(),
        organization_slug: organizationSlug.trim().toLowerCase(),
        full_name: ownerName.trim(),
        email,
        password,
      }, bootstrapSecret.trim() || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося створити першу організацію");
    } finally {
      setLoading(false);
    }
  };

  return <div className="loginScreen">
    <button className="loginThemeToggle" type="button" aria-label={theme === "dark" ? "Увімкнути світлу тему" : "Увімкнути темну тему"} title={theme === "dark" ? "Світла тема" : "Темна тема"} onClick={onToggleTheme}><UiIcon name="theme" size={18} /><span>Тема</span></button>
    <div className="loginCard">
      <div className="loginBrand"><img className="brandLogo brandLogoLarge" src="/aerokids-logo-master-v1.png" alt="AeroKids" /><div><b>AeroKids CRM</b><small>Керування школою в одному місці</small></div></div>

      {resetToken ? <>
        <p className="eyebrow">Новий пароль</p>
        <h1>Створіть новий пароль</h1>
        <p className="loginIntro">Посилання одноразове. Після збереження ви одразу ввійдете у CRM.</p>
        <form onSubmit={completePasswordReset}>
          <label>Новий пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Зберігаємо…" : "Змінити пароль"}</button>
        </form>
      </> : inviteToken ? inviteStatus === "checking" ? <>
        <div className="loginChecking">Перевіряємо запрошення…</div>
      </> : inviteStatus === "accepted" ? <>
        <p className="eyebrow">Запрошення використано</p>
        <h1>Вже зареєстровано</h1>
        <p className="loginIntro">За цим посиланням уже зареєстровано користувача. Запрошення одноразове і більше не активне.</p>
        <a className="primary full inviteLoginLink" href="/">Перейти до входу</a>
      </> : inviteStatus === "expired" ? <>
        <p className="eyebrow">Запрошення неактивне</p>
        <h1>Термін дії минув</h1>
        <p className="loginIntro">Це посилання на запрошення вже прострочене. Попросіть адміністратора створити нове.</p>
        <a className="primary full inviteLoginLink" href="/">Перейти до входу</a>
      </> : inviteStatus === "invalid" ? <>
        <p className="eyebrow">Запрошення недійсне</p>
        <h1>Посилання не працює</h1>
        <p className="loginIntro">Перевірте, чи посилання скопійовано повністю, або попросіть адміністратора створити нове запрошення.</p>
        <a className="primary full inviteLoginLink" href="/">Перейти до входу</a>
      </> : inviteStatus === "error" ? <>
        <p className="eyebrow">Не вдалося перевірити</p>
        <h1>Спробуйте ще раз</h1>
        <p className="loginIntro">CRM тимчасово не змогла перевірити це запрошення.</p>
        <button className="primary full" type="button" onClick={() => window.location.reload()}>Повторити перевірку</button>
      </> : <>
        <p className="eyebrow">Запрошення</p>
        <h1>Створіть свій доступ</h1>
        <p className="loginIntro">Вкажіть ім’я та пароль. Роль і організація вже задані запрошенням. Це посилання можна використати лише один раз.</p>
        <form onSubmit={acceptInvitation}>
          <label>Ваше ім’я<input autoComplete="name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} required /></label>
          <label>Пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Створюємо доступ…" : "Прийняти запрошення"}</button>
        </form>
      </> : checkingBootstrap ? <div className="loginChecking">Перевіряємо CRM…</div> : bootstrapAvailable ? <>
        <p className="eyebrow">Перший запуск</p>
        <h1>Створіть першу організацію</h1>
        <p className="loginIntro">Це виконується один раз. Після цього ви станете власником організації та зможете запрошувати команду.</p>
        <form onSubmit={setup}>
          <label>Назва організації<input value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} required /></label>
          <label>Короткий slug<input value={organizationSlug} onChange={(e) => setOrganizationSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))} required /></label>
          <label>Ваше ім’я<input autoComplete="name" value={ownerName} onChange={(e) => setOwnerName(e.target.value)} required /></label>
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль<input type="password" minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <label>Ключ першого запуску<input type="password" autoComplete="off" value={bootstrapSecret} onChange={(e) => setBootstrapSecret(e.target.value)} placeholder="Задається в Render → aerokids-crm-api → Environment" required /></label>
          <small className="setupHint">Введіть значення BOOTSTRAP_SECRET із налаштувань backend у Render.</small>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full" disabled={loading}>{loading ? "Створюємо…" : "Створити CRM"}</button>
        </form>
      </> : <>
        <p className="eyebrow">Вхід</p>
        <h1>Увійдіть у CRM</h1>
        <p className="loginIntro">Використовуйте email і пароль вашого облікового запису.</p>
        <form onSubmit={submit}>
          <label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Пароль<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="loginError">{error}</div>}
          <button className="primary full loginAction" disabled={loading}><UiIcon name="login" size={18} /><span>{loading ? "Входимо…" : "Увійти"}</span></button>
        </form>
        <small className="loginNote">Доступ визначається роллю в конкретній організації.</small>
      </>}
    </div>
  </div>;
}

