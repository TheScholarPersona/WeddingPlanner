import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { Card, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api/client';

import { projectPath, taskKeys, type ActivityPage } from './api';

export function ActivityFeed({ org, projectId }: { org: string; projectId: string }) {
  const { t, i18n } = useTranslation();
  const feed = useQuery({
    queryKey: taskKeys.activity(org, projectId),
    queryFn: () => api<ActivityPage>('GET', `${projectPath(org, projectId)}/activity?limit=8`),
  });
  const items = feed.data?.items ?? [];

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('activity.title')}</CardTitle>
      {items.length === 0 && <p className="text-sm text-muted">{t('activity.empty')}</p>}
      <ul className="flex flex-col gap-2.5">
        {items.map((event) => (
          <li key={event.id} className="text-sm">
            <span className="font-semibold">{event.actor_name ?? t('settings.system')}</span>{' '}
            {i18n.exists(`activity.verbs.${event.verb}`)
              ? t(`activity.verbs.${event.verb}` as never)
              : event.verb}{' '}
            <span className="text-ink-soft">“{event.summary}”</span>
            <span className="block text-xs text-muted">
              {new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(
                new Date(event.created_at),
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
