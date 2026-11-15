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
