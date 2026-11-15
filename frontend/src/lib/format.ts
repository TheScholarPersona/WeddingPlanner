/**
 * Dates, numbers and money follow the organization's locale setting (default de-DE),
 * while UI copy stays English. The locale will come from the organization in Sprint 1.
 */
export const DEFAULT_FORMAT_LOCALE = 'de-DE';

export function formatDate(value: Date | string, locale = DEFAULT_FORMAT_LOCALE): string {
  // Plain dates ("2027-06-12") are calendar dates; read them at noon to avoid time-zone shifts.
  const date =
    typeof value === 'string'
      ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value)
      : value;
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

export function formatMoney(
  amountCents: number,
  currency = 'EUR',
  locale = DEFAULT_FORMAT_LOCALE,
): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(amountCents / 100);
}

/** Calendar parts for a date badge, e.g. { month: 'JUN', day: '12' }. */
export function dateBadge(value: string): { month: string; day: string } {
  const date = new Date(`${value}T12:00:00`);
  return {
    month: new Intl.DateTimeFormat('en', { month: 'short' }).format(date).toUpperCase(),
    day: String(date.getDate()).padStart(2, '0'),
  };
}

/** Offset in days relative to the wedding, as a short English phrase. */
export function describeOffset(days: number): string {
  if (days === 0) return 'On the wedding day';
  const abs = Math.abs(days);
  const when = days < 0 ? 'before' : 'after';
  if (abs % 30 === 0 && abs >= 60) return `${abs / 30} months ${when}`;
  if (abs % 7 === 0 && abs >= 14) return `${abs / 7} weeks ${when}`;
  return `${abs} ${abs === 1 ? 'day' : 'days'} ${when}`;
}

export function formatTime(value: string, locale = DEFAULT_FORMAT_LOCALE): string {
  return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(
    new Date(value),
  );
}

/** "12 Jun" style day and month, e.g. for agenda rows. */
export function formatDayMonth(value: string, locale = DEFAULT_FORMAT_LOCALE): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(
    new Date(`${value}T12:00:00`),
  );
}

export function formatFileSize(bytes: number, locale = DEFAULT_FORMAT_LOCALE): string {
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 10 ? 0 : 1;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value)} ${units[unit]}`;
}

/** Local calendar date "YYYY-MM-DD" of a Date (no UTC shift). */
export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
