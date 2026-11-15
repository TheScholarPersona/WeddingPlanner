import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import { formatDate } from '@/lib/format';

export function DashboardPage() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <span className="text-sm text-muted">{formatDate(new Date())}</span>
        <h1 className="font-display text-[44px] leading-tight font-medium">
          {t('planner.dashboard.greeting')}
        </h1>
      </header>
      <EmptyState
        title={t('planner.dashboard.emptyTitle')}
        body={t('planner.dashboard.emptyBody')}
      />
    </div>
  );
}
