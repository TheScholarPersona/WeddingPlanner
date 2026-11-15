import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatMoney, formatTime, isoDate } from '@/lib/format';
import { cn } from '@/lib/utils';

import { calendarKeys, itemLink, itemsOn, monthGrid, type CalendarItem } from './api';
import { FeedDialog } from './FeedDialog';

const KIND_STYLE: Record<CalendarItem['kind'], string> = {
  wedding: 'bg-accent text-white',
  event: 'bg-accent-tint text-accent-strong',
  task: 'border border-line bg-surface text-ink-soft',
  payment: 'bg-warning-soft text-warning',
};

export function CalendarPage() {
  const { t, i18n } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [mine, setMine] = useState(false);
  const [subscribing, setSubscribing] = useState(false);

  const days = useMemo(() => monthGrid(month), [month]);
  const start = isoDate(days[0]!);
  const end = isoDate(days[days.length - 1]!);
  const items = useQuery({
    queryKey: calendarKeys.range(org, start, end, mine),
    queryFn: () =>
      api<CalendarItem[]>('GET', `/orgs/${org}/calendar?start=${start}&end=${end}&mine=${mine}`),
  });

  const today = isoDate(new Date());
  const monthLabel = new Intl.DateTimeFormat(i18n.language, {
    month: 'long',
    year: 'numeric',
  }).format(month);
  const shift = (delta: number) =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1));
  const weekdays = days
    .slice(0, 7)
    .map((d) => new Intl.DateTimeFormat(i18n.language, { weekday: 'short' }).format(d));
  const inMonth = (d: Date) => d.getMonth() === month.getMonth();
  const agendaDays = days.filter(inMonth).map(isoDate);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t('calendar.title')}
        actions={
          <Button variant="secondary" onClick={() => setSubscribing(true)}>
            {t('calendar.feed.button')}
          </Button>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="icon"
            aria-label={t('calendar.previousMonth')}
            onClick={() => shift(-1)}
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
          </Button>
          <h2
            className="min-w-44 text-center font-display text-2xl font-semibold"
            aria-live="polite"
          >
            {monthLabel}
          </h2>
          <Button
            variant="secondary"
            size="icon"
            aria-label={t('calendar.nextMonth')}
            onClick={() => shift(1)}
          >
            <ChevronRight aria-hidden="true" className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}
          >
            {t('calendar.today')}
          </Button>
        </div>
        <label className="flex items-center gap-2.5 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-accent"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
          />
          {t('calendar.onlyMyTasks')}
        </label>
      </div>

      <Legend />

      {items.isPending ? (
        <Spinner />
      ) : items.error ? (
        <FormMessage>{errorMessage(items.error, t)}</FormMessage>
      ) : (
        <>
          {/* Month grid: tablets and desktops */}
          <Card className="hidden overflow-hidden p-0 md:block">
            <div className="grid grid-cols-7 border-b border-line bg-subtle text-xs font-medium text-muted">
              {weekdays.map((day) => (
                <div key={day} className="px-2 py-2">
                  {day}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {days.map((day) => {
                const key = isoDate(day);
                const dayItems = itemsOn(items.data, key);
                return (
                  <div
                    key={key}
                    className={cn(
                      'flex min-h-28 flex-col gap-1 border-r border-b border-line-soft p-1.5 [&:nth-child(7n)]:border-r-0',
                      !inMonth(day) && 'bg-ground/60',
                    )}
                  >
                    <span
                      className={cn(
                        'self-end rounded-full px-1.5 text-xs',
                        key === today && 'bg-accent font-semibold text-white',
                        !inMonth(day) && 'text-muted',
                      )}
                    >
                      {day.getDate()}
                    </span>
                    {dayItems.slice(0, 4).map((item) => (
                      <Chip key={`${item.kind}-${item.id}`} item={item} />
                    ))}
                    {dayItems.length > 4 && (
                      <span className="px-1 text-[11px] text-muted">
                        {t('calendar.more', { count: dayItems.length - 4 })}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Agenda: phones */}
          <div className="flex flex-col gap-4 md:hidden">
            {agendaDays.every((d) => itemsOn(items.data, d).length === 0) && (
              <p className="text-sm text-muted">{t('calendar.nothingThisMonth')}</p>
            )}
            {agendaDays.map((day) => {
              const dayItems = itemsOn(items.data, day);
              if (!dayItems.length) return null;
              return (
                <section key={day} className="flex flex-col gap-2">
                  <h3
                    className={cn('text-sm font-semibold', day === today && 'text-accent-strong')}
                  >
                    {new Intl.DateTimeFormat(i18n.language, {
                      weekday: 'long',
                      day: 'numeric',
                      month: 'long',
                    }).format(new Date(`${day}T12:00:00`))}
                  </h3>
                  <ul className="flex flex-col gap-1.5">
                    {dayItems.map((item) => (
                      <li key={`${item.kind}-${item.id}`}>
                        <Chip item={item} large />
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        </>
      )}

      {subscribing && (
        <FeedDialog
          path={`/orgs/${org}/calendar/feed`}
          queryKey={calendarKeys.feed(org)}
          onClose={() => setSubscribing(false)}
        />
      )}
    </div>
  );
}

function Chip({ item, large = false }: { item: CalendarItem; large?: boolean }) {
  const { t } = useTranslation();
  const time = item.kind === 'event' && !item.all_day && item.starts_at;
  const prefix =
    item.kind === 'task' ? t('calendar.kinds.due') : item.kind === 'payment' ? '€ ' : '';
  const done = item.kind === 'task' && item.status === 'done';
  return (
    <Link
      to={itemLink(item)}
      title={`${item.title} · ${item.project_title}`}
      className={cn(
        'block truncate rounded-md px-1.5 py-0.5 text-[11px] leading-snug hover:brightness-95',
        KIND_STYLE[item.kind],
        large && 'rounded-lg px-3 py-2 text-sm',
        done && 'line-through opacity-60',
      )}
    >
      {time && <span className="font-semibold">{formatTime(item.starts_at!)} </span>}
      {prefix}
      {item.kind === 'wedding' ? t('calendar.kinds.wedding', { title: item.title }) : item.title}
      {large && item.kind !== 'wedding' && (
        <span className="block text-xs opacity-80">
          {item.project_title}
          {item.amount_cents != null && ` · ${formatMoney(item.amount_cents)}`}
          {item.location && ` · ${item.location}`}
        </span>
      )}
    </Link>
  );
}

function Legend() {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-muted" aria-label={t('calendar.legend')}>
      {(Object.keys(KIND_STYLE) as CalendarItem['kind'][]).map((kind) => (
        <li key={kind} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={cn('size-3 rounded-sm ring-1 ring-line', KIND_STYLE[kind])}
          />
          {t(`calendar.legendKinds.${kind}`)}
        </li>
      ))}
    </ul>
  );
}
