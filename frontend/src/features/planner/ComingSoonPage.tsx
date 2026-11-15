import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';

export function ComingSoonPage() {
  const { t } = useTranslation();
  return <EmptyState title={t('planner.comingSoon.title')} body={t('planner.comingSoon.body')} />;
}
