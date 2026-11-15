import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, weddingPath, type Wedding } from '@/features/weddings/api';
import { WeddingNav } from '@/features/weddings/WeddingNav';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { isoDate } from '@/lib/format';

import { calendarKeys, eventsPath, type CalendarEvent } from './api';
import { EventDialog } from './EventDialog';
import { EventList, type AgendaEntry } from './EventList';

export function WeddingCalendarPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [editing, setEditing] = useState<CalendarEvent | 'new' | null>(null);
  const [showPast, setShowPast] = useState(false);

  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });
  const events = useQuery({
    queryKey: calendarKeys.events(org, id),
    queryFn: () => api<CalendarEvent[]>('GET', eventsPath(org, id)),
  });

  if (wedding.isPending || events.isPending) return <Spinner />;
  if (!wedding.data || !events.data) {
    return <FormMessage>{errorMessage(wedding.error ?? events.error, t)}</FormMessage>;
  }
  const canEdit = wedding.data.permissions.includes('events:write');
  const today = isoDate(new Date());
  const entry = (e: CalendarEvent): AgendaEntry => ({ ...e, shared: e.visibility === 'client' });
  const upcoming = events.data.filter((e) => e.end_date >= today).map(entry);
  const past = events.data
    .filter((e) => e.end_date < today)
    .reverse()
    .map(entry);
  const open = canEdit
    ? (eventId: string) => setEditing(events.data.find((e) => e.id === eventId) ?? null)
    : undefined;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{t('calendar.weddingIntro')}</p>
        {canEdit && <Button onClick={() => setEditing('new')}>{t('calendar.newEvent')}</Button>}
      </div>

      {events.data.length === 0 ? (
        <EmptyState title={t('calendar.emptyTitle')} body={t('calendar.emptyBody')} />
      ) : (
        <>
          <Card className="flex flex-col gap-1">
            <CardTitle>{t('calendar.upcoming')}</CardTitle>
            {upcoming.length ? (
              <EventList entries={upcoming} onOpen={open} />
            ) : (
              <p className="py-3 text-sm text-muted">{t('calendar.noUpcoming')}</p>
            )}
          </Card>
          {past.length > 0 && (
            <Card className="flex flex-col gap-1">
              <CardTitle>
                <button
                  type="button"
                  className="text-left"
                  aria-expanded={showPast}
                  onClick={() => setShowPast((v) => !v)}
                >
                  {t('calendar.past', { count: past.length })}
                </button>
              </CardTitle>
              {showPast && <EventList entries={past} onOpen={open} />}
            </Card>
          )}
        </>
      )}

      {editing && (
        <EventDialog
          key={editing === 'new' ? 'new' : `${editing.id}-${editing.version}`}
          org={org}
          projectId={id}
          event={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
