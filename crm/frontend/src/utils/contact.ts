export function cleanSpaces(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

export function personNameError(value: string, label = "Ім’я"): string {
  const name = cleanSpaces(value);
  if (!name) return label + " обов’язкове";
  if (name.length < 2) return label + " має містити щонайменше 2 символи";
  if (name.length > 160) return label + " занадто довге";
  if (!/^[A-Za-zА-Яа-яІіЇїЄєҐґ'’\- ]+$/.test(name)) return label + ": лише літери, пробіл, апостроф або дефіс";
  if (/^[ '’\-]|[ '’\-]$|[ '’\-]{2,}/.test(name)) return "Перевірте написання поля «" + label + "»";
  return "";
}

export function fullNameError(value: string, label: string): string {
  const basic = personNameError(value, label);
  if (basic) return basic;
  if (cleanSpaces(value).split(" ").filter(Boolean).length < 2) return label + ": вкажіть ім’я та прізвище";
  return "";
}


export function normalizeUaPhone(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  let national = "";
  if (digits.startsWith("380") && digits.length === 12) national = digits.slice(3);
  else if (digits.startsWith("0") && digits.length === 10) national = digits.slice(1);
  else if (digits.length === 9) national = digits;
  else return null;
  if (!/^[3-9]\d{8}$/.test(national)) return null;
  return "+380" + national;
}

export function uaPhoneError(value: string, required = true): string {
  if (!value.trim()) return required ? "Телефон обов’язковий" : "";
  return normalizeUaPhone(value) ? "" : "Некоректний номер України. Приклад: +380 67 123 45 67";
}

export function formatUaPhone(value: string): string {
  const normalized = normalizeUaPhone(value);
  if (!normalized) return value;
  const n = normalized.slice(4);
  return "+380 " + n.slice(0, 2) + " " + n.slice(2, 5) + " " + n.slice(5, 7) + " " + n.slice(7, 9);
}

export function normalizedSearch(value: string) {
  return cleanSpaces(value).toLocaleLowerCase("uk-UA");
}

export function searchMatches(query: string, value: string | null | undefined) {
  if (!value) return false;
  if (normalizedSearch(value).includes(query)) return true;
  const queryDigits = query.replace(/\D/g, "");
  const valueDigits = value.replace(/\D/g, "");
  return queryDigits.length >= 3 && valueDigits.includes(queryDigits);
}

