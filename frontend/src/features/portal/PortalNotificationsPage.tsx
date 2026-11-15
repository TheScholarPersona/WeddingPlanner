import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import { Spinner } from '@/components/Spinner';
import { NotificationSettings } from '@/features/notifications/NotificationSettings';

import { portalPath, usePortalProject } from './api';

export function PortalNotificationsPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  if (isPending) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-4xl font-medium">{t('notifications.title')}</h1>
      <p className="text-sm text-ink-soft">{t('notifications.coupleIntro')}</p>
      <NotificationSettings
        path={`${portalPath(project.id)}/notification-preferences`}
        queryKey={['portal', project.id, 'notification-preferences']}
        audience="couple"
      />
      <p className="text-xs text-muted">{t('notifications.privacy')}</p>
    </div>
  );
}
