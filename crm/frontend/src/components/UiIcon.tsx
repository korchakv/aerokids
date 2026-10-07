export type UiIconName = "home" | "leads" | "student" | "groups" | "calendar" | "attendance" | "wallet" | "staff" | "location" | "reports" | "settings" | "search" | "logout" | "login" | "plus" | "sun" | "moon" | "theme" | "edit" | "x" | "back";

export function UiIcon({ name, size = 18 }: { name: UiIconName; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "home": return <svg {...common}><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>;
    case "leads": return <svg {...common}><path d="M8 7h8"/><path d="M8 11h5"/><path d="M5 3h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4v-4H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/></svg>;
    case "student": return <svg {...common}><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6"/></svg>;
    case "groups": return <svg {...common}><circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2.5"/><path d="M3.5 20c.7-4 2.5-6 5.5-6s4.8 2 5.5 6"/><path d="M14 15c3.3-.6 5.5 1 6.5 4"/></svg>;
    case "calendar": return <svg {...common}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/><path d="M8 14h2M14 14h2M8 18h2"/></svg>;
    case "attendance": return <svg {...common}><path d="M9 5H6a2 2 0 0 0-2 2v13h16V7a2 2 0 0 0-2-2h-3"/><path d="M9 3h6v4H9z"/><path d="m8 14 2.5 2.5L16 11"/></svg>;
    case "wallet": return <svg {...common}><path d="M4 6h14a2 2 0 0 1 2 2v11H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h11"/><path d="M15 11h6v5h-6a2.5 2.5 0 0 1 0-5Z"/></svg>;
    case "staff": return <svg {...common}><circle cx="9" cy="8" r="3"/><path d="M3.5 20c.7-4 2.5-6 5.5-6 1.7 0 3 .5 4 1.4"/><path d="M17 13v6M14 16h6"/></svg>;
    case "location": return <svg {...common}><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></svg>;
    case "reports": return <svg {...common}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>;
    case "settings": return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7-.7-1.7.9-1.9-2.1-2.1-1.9.9-1.7-.7L10.5 2h-3l-.7 2-1.7.7-1.9-.9L1.1 5.9l.9 1.9-.7 1.7-2 .7v3l2 .7.7 1.7-.9 1.9 2.1 2.1 1.9-.9 1.7.7.7 2h3l.7-2 1.7-.7 1.9.9 2.1-2.1-.9-1.9.7-1.7Z" transform="translate(2.5 0) scale(.78)"/></svg>;
    case "search": return <svg {...common}><circle cx="11" cy="11" r="6.5"/><path d="m16 16 5 5"/></svg>;
    case "logout": return <svg {...common}><path d="M10 4H5v16h5"/><path d="M14 8l4 4-4 4M18 12H9"/></svg>;
    case "login": return <svg {...common}><path d="M14 4h5v16h-5"/><path d="m10 8-4 4 4 4M6 12h9"/></svg>;
    case "plus": return <svg {...common}><path d="M12 5v14M5 12h14"/></svg>;
    case "sun": return <svg {...common}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
    case "moon": return <svg {...common}><path d="M20 15.5A8 8 0 1 1 8.5 4 6.5 6.5 0 0 0 20 15.5Z"/></svg>;
    case "theme": return <svg {...common}><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none"/></svg>;
    case "edit": return <svg {...common}><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z"/><path d="m13.8 8.2 3 3"/></svg>;
    case "x": return <svg {...common}><path d="m6 6 12 12M18 6 6 18"/></svg>;
    case "back": return <svg {...common}><path d="m15 18-6-6 6-6"/><path d="M9 12h11"/></svg>;
  }
}

export function navigationIcon(item: string): UiIconName {
  const map: Record<string, UiIconName> = {
    "Дашборд": "home", "Заявки": "leads", "Учні": "student", "Групи": "groups",
    "Розклад": "calendar", "Відвідування": "attendance", "Оплати": "wallet",
    "Працівники": "staff", "Локації": "location", "Звіти": "reports", "Налаштування": "settings",
  };
  return map[item] ?? "home";
}

