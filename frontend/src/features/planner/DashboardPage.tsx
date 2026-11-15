import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { StatTile } from '@/components/StatTile';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { useMe } from '@/features/auth/session';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, type Dashboard } from '@/features/weddings/api';
import { WeddingRow } from '@/features/weddings/WeddingRow';
import { api } from '@/lib/api/client';
import { formatDate } from '@/lib/format';

export function DashboardPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const board = useQuery({
    queryKey: keys.dashboard(org),
    queryFn: () => api<Dashboard>('GET', `/orgs/${org}/dashboard`),
  });
  const firstName = me?.full_name.split(' ')[0] ?? '';

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow={formatDate(new Date())}
        title={t('planner.dashboard.greeting', { name: firstName })}
        actions={
          <Button asChild>
            <Link to="/app/weddings/new">{t('weddings.new')}</Link>
          </Button>
        }
      />
      {!board.data ? (
        <Spinner />
      ) : (
        <>
          <section
            aria-label={t('planner.dashboard.keyFigures')}
            className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
          >
            <StatTile
              label={t('planner.dashboard.activeWeddings')}
              value={board.data.active_weddings}
              hint={t('planner.dashboard.nextSixMonths', {
                count: board.data.weddings_next_6_months,
              })}
            />
            <StatTile
              label={t('planner.dashboard.dueThisWeek')}
              value={board.data.tasks_due_this_week}
              hint={t('planner.dashboard.assignedToYou', {
                count: board.data.tasks_due_this_week_mine,
              })}
            />
            <StatTile
              label={t('planner.dashboard.overdue')}
              value={board.data.overdue_tasks}
              tone={board.data.overdue_tasks > 0 ? 'danger' : 'default'}
              hint={t('planner.dashboard.acrossWeddings', { count: board.data.overdue_weddings })}
            />
          </section>
          {board.data.upcoming.length === 0 ? (
            <EmptyState
              title={t('planner.dashboard.emptyTitle')}
              body={t('planner.dashboard.emptyBody')}
            />
          ) : (
            <Card className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between">
                <CardTitle>{t('planner.dashboard.upcoming')}</CardTitle>
                <Link to="/app/weddings" className="text-sm font-medium text-accent">
                  {t('common.viewAll')}
                </Link>
              </div>
              <div>
                {board.data.upcoming.map((wedding) => (
                  <WeddingRow key={wedding.id} wedding={wedding} />
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
