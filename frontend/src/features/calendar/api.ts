import type { Schemas } from '@/lib/api/client';
import { formatDate, formatTime, isoDate } from '@/lib/format';

export type CalendarEvent = Schemas['EventOut'];
export type EventInput = Schemas['EventIn'];
export type CalendarItem = Schemas['CalendarItemOut'];
export type Feed = Schemas['FeedOut'];
export type FeedCreated = Schemas['FeedCreatedOut'];

export const calendarKeys = {
  events: (org: string, project: string) => ['org', org, 'wedding', project, 'events'] as const,
  range: (org: string, start: string, end: string, mine: boolean) =>
    ['org', org, 'calendar', start, end, mine] as const,
  feed: (org: string) => ['org', org, 'calendar', 'feed'] as const,
};

export const eventsPath = (org: string, project: string) =>
  `/orgs/${org}/projects/${project}/events`;

/** Monday-based weeks covering the whole month of `month` (first day of the month). */
export function monthGrid(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7; // Monday = 0
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const days = Math.ceil((offset + last.getDate()) / 7) * 7;
  return Array.from({ length: days }, (_, i) => {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    return day;
  });
}

/** Items that cover a given day (multi-day events appear on every day). */
export function itemsOn(items: CalendarItem[], day: string): CalendarItem[] {
  return items.filter((i) => i.date <= day && day <= i.end_date);
}

/** Where an item opens in the planner app. */
export function itemLink(item: CalendarItem): string {
  const base = `/app/weddings/${item.project_id}`;
  switch (item.kind) {
    case 'event':
      return `${base}/calendar`;
    case 'task':
      return `${base}/tasks?task=${item.id}`;
    case 'payment':
      return `${base}/budget`;
    default:
      return base;
  }
}

/** Local date and time inputs for an ISO timestamp. */
export function toLocalInputs(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return { date: isoDate(d), time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

/** "2027-06-12" + "15:30" in the browser's time zone → ISO timestamp with offset (UTC). */
export function fromLocalInputs(date: string, time: string): string {
  return new Date(`${date}T${time || '00:00'}:00`).toISOString();
}

/** Something with a date that can be shown as an appointment row. */
export interface AgendaEntry {
  id: string;
  title: string;
  start_date: string;
  end_date: string;
  all_day: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  location?: string | null;
  shared?: boolean;
  label?: string;
}

export function timeLabel(entry: AgendaEntry, allDayText: string): string {
  if (entry.all_day || !entry.starts_at) {
    return entry.end_date !== entry.start_date
      ? `${formatDate(entry.start_date)} – ${formatDate(entry.end_date)}`
      : allDayText;
  }
  return entry.ends_at
    ? `${formatTime(entry.starts_at)} – ${formatTime(entry.ends_at)}`
    : formatTime(entry.starts_at);
}
