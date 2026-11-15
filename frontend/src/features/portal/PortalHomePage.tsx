import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';

export function PortalHomePage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-4xl font-medium">{t('portal.home.greeting')}</h1>
      <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />
    </div>
  );
}
