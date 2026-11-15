/**
 * Dates, numbers and money follow the organization's locale setting (default de-DE),
 * while UI copy stays English. The locale will come from the organization in Sprint 1.
 */
export const DEFAULT_FORMAT_LOCALE = 'de-DE';

export function formatDate(value: Date | string, locale = DEFAULT_FORMAT_LOCALE): string {
  const date = typeof value === 'string' ? new Date(value) : value;
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
