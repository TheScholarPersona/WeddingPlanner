import { useTranslation } from 'react-i18next';

import { EmptyState } from '@/components/EmptyState';
import { useMe } from '@/features/auth/session';
import { formatDate } from '@/lib/format';

export function DashboardPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const firstName = me?.full_name.split(' ')[0] ?? '';
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <span className="text-sm text-muted">{formatDate(new Date())}</span>
        <h1 className="font-display text-[44px] leading-tight font-medium">
          {t('planner.dashboard.greeting', { name: firstName })}
        </h1>
      </header>
      <EmptyState
        title={t('planner.dashboard.emptyTitle')}
        body={t('planner.dashboard.emptyBody')}
      />
    </div>
  );
}
