import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import { useMe } from '@/features/auth/session';

export function PortalHomePage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-4xl font-medium">
        {t('portal.home.greeting', { name: me?.full_name.split(' ')[0] ?? '' })}
      </h1>
      <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />
    </div>
  );
}
