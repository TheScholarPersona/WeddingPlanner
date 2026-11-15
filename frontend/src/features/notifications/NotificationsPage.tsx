import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/PageHeader';
import { useActiveOrg } from '@/features/auth/useActiveOrg';

import { NotificationSettings } from './NotificationSettings';

export function NotificationsPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <PageHeader title={t('notifications.title')} />
      <p className="text-sm text-ink-soft">
        {t('notifications.intro', { organization: membership.organization_name })}
      </p>
      <NotificationSettings
        path={`/orgs/${org}/notification-preferences`}
        queryKey={['org', org, 'notification-preferences']}
        audience="team"
      />
      <p className="text-xs text-muted">{t('notifications.privacy')}</p>
    </div>
  );
}
