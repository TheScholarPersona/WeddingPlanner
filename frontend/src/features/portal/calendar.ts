import { useQuery } from '@tanstack/react-query';

import type { AgendaEntry } from '@/features/calendar/api';
import { api, type Schemas } from '@/lib/api/client';
import { formatMoney, isoDate } from '@/lib/format';

import { portalPath } from './api';

type Item = Schemas['PortalCalendarItem'];

export function usePortalCalendar(projectId: string | undefined, days = 365) {
  const start = isoDate(new Date());
  const endDate = new Date();
  endDate.setDate(endDate.getDate() + days);
  const end = isoDate(endDate);
  return useQuery({
    queryKey: ['portal', projectId, 'calendar', start, end],
    queryFn: () =>
      api<Item[]>('GET', `${portalPath(projectId!)}/calendar?start=${start}&end=${end}`),
    enabled: !!projectId,
  });
}

export function toAgenda(items: Item[], t: (key: string, o?: object) => string): AgendaEntry[] {
  return items
    .filter((i) => !(i.kind === 'task' && i.status === 'done'))
    .map((i) => ({
      id: `${i.kind}-${i.id}`,
      title:
        i.kind === 'wedding'
          ? t('portal.calendar.weddingDay')
          : i.kind === 'task'
            ? t('portal.calendar.due', { title: i.title })
            : i.title,
      start_date: i.date,
      end_date: i.end_date,
      all_day: i.all_day,
      starts_at: i.starts_at,
      ends_at: i.ends_at,
      location: i.location,
      label:
        i.kind === 'payment' && i.amount_cents != null
          ? t('portal.calendar.payment', { amount: formatMoney(i.amount_cents) })
          : undefined,
    }));
}
