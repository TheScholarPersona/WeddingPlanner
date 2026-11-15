import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EventList } from '@/features/calendar/EventList';
import { FeedDialog } from '@/features/calendar/FeedDialog';
import { errorMessage } from '@/lib/api/errors';

import { usePortalProject, portalPath } from './api';
import { toAgenda, usePortalCalendar } from './calendar';

export function PortalCalendarPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  const items = usePortalCalendar(project?.id);
  const [subscribing, setSubscribing] = useState(false);

  if (isPending || (project && items.isPending)) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  if (!items.data) return <FormMessage>{errorMessage(items.error, t)}</FormMessage>;
  const entries = toAgenda(items.data, t as never);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-3">
        <h1 className="font-display text-4xl font-medium">{t('portal.calendar.title')}</h1>
        <Button size="sm" variant="secondary" onClick={() => setSubscribing(true)}>
          {t('portal.calendar.subscribe')}
        </Button>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t('portal.calendar.empty')}</p>
      ) : (
        <Card className="py-1">
          <EventList entries={entries} />
        </Card>
      )}
      {subscribing && (
        <FeedDialog
          path={`${portalPath(project.id)}/calendar/feed`}
          queryKey={['portal', project.id, 'calendar', 'feed']}
          onClose={() => setSubscribing(false)}
        />
      )}
    </div>
  );
}
