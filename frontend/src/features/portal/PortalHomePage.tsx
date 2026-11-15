import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { useMe } from '@/features/auth/session';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { dateBadge, formatDate, formatMoney } from '@/lib/format';

import { portalKeys, portalPath, textOn, usePortalProject, type PortalOverview } from './api';
import { EventList } from '@/features/calendar/EventList';

import { toAgenda, usePortalCalendar } from './calendar';
import { PortalTaskItem } from './PortalTaskItem';

const DEFAULT_ACCENT = '#33443a';

export function PortalHomePage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const { project, isPending, error } = usePortalProject();
  const overview = useQuery({
    queryKey: portalKeys.overview(project?.id ?? ''),
    queryFn: () => api<PortalOverview>('GET', portalPath(project!.id)),
    enabled: !!project,
  });
  const calendar = usePortalCalendar(project?.id, 120);

  if (isPending || (project && overview.isPending)) return <Spinner />;
  if (error || overview.error)
    return <FormMessage>{errorMessage(error ?? overview.error, t)}</FormMessage>;
  if (!project || !overview.data) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  const data = overview.data;
  const accent = data.organization.accent_color ?? DEFAULT_ACCENT;
  const ink = textOn(accent);
  const firstName = me?.full_name.split(' ')[0] ?? '';
  const upcoming = data.milestones.filter((m) => !m.completed).slice(0, 3);
  const appointments = toAgenda(
    (calendar.data ?? []).filter((i) => i.kind === 'event'),
    t as never,
  ).slice(0, 3);

  return (
    <div className="flex flex-col gap-6">
      <section
        className="flex flex-col gap-1.5 rounded-[18px] p-6"
        style={{ backgroundColor: accent, color: ink }}
      >
        <span className="text-sm opacity-85">{t('portal.home.greeting', { name: firstName })}</span>
        {data.days_to_go != null && data.days_to_go >= 0 ? (
          <div className="flex items-baseline gap-2.5">
            <span className="font-display text-[64px] leading-none font-medium">
              {data.days_to_go}
            </span>
            <span className="text-[15px]">
              {t('portal.home.daysToGo', { count: data.days_to_go })}
            </span>
          </div>
        ) : (
          <span className="font-display text-4xl font-medium">{data.title}</span>
        )}
        <span className="text-sm opacity-85">
          {[data.wedding_date ? formatDate(data.wedding_date) : null, data.venue_name]
            .filter(Boolean)
            .join(' · ')}
        </span>
        <div className="mt-3 flex flex-col gap-1.5">
          <div
            role="progressbar"
            aria-label={t('portal.home.progress')}
            aria-valuenow={data.progress.percent}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1.5 rounded-full"
            style={{ backgroundColor: `${ink}33` }}
          >
            <div
              className="h-1.5 rounded-full"
              style={{ width: `${data.progress.percent}%`, backgroundColor: ink }}
            />
          </div>
          <span className="text-xs opacity-85">
            {t('portal.home.planningComplete', { percent: data.progress.percent })}
          </span>
        </div>
      </section>

      <section className="flex flex-col gap-2.5">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-2xl font-semibold">{t('portal.home.nextSteps')}</h2>
          <Link to="/portal/tasks" className="text-sm font-medium text-accent">
            {t('portal.home.seeAll')}
          </Link>
        </div>
        {data.next_steps.length === 0 ? (
          <p className="text-sm text-muted">{t('portal.home.allDone')}</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {data.next_steps.slice(0, 3).map((task) => (
              <PortalTaskItem key={task.id} projectId={data.id} task={task} />
            ))}
          </ul>
        )}
      </section>

      {appointments.length > 0 && (
        <section className="flex flex-col gap-2.5">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl font-semibold">{t('portal.home.appointments')}</h2>
            <Link to="/portal/calendar" className="text-sm font-medium text-accent">
              {t('portal.home.seeAll')}
            </Link>
          </div>
          <div className="rounded-xl border border-line bg-surface px-4">
            <EventList entries={appointments} />
          </div>
        </section>
      )}

      {upcoming.length > 0 && (
        <section className="flex flex-col gap-2.5">
          <h2 className="font-display text-2xl font-semibold">{t('portal.home.comingUp')}</h2>
          <ul className="flex flex-col gap-2.5">
            {upcoming.map((milestone) => {
              const badge = milestone.due_date ? dateBadge(milestone.due_date) : null;
              return (
                <li
                  key={milestone.id}
                  className="flex items-center gap-3.5 rounded-xl border border-line bg-surface px-4 py-3"
                >
                  <div className="flex w-11 flex-col items-center">
                    {badge && (
                      <>
                        <span className="text-[11px] font-semibold text-muted">{badge.month}</span>
                        <span className="font-display text-2xl leading-none font-semibold">
                          {badge.day}
                        </span>
                      </>
                    )}
                  </div>
                  <span className="text-[15px] font-medium">{milestone.title}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <Link
        to="/portal/budget"
        className="flex items-center justify-between rounded-xl border border-line bg-surface p-4 text-ink"
      >
        <span className="flex flex-col gap-0.5">
          <span className="text-sm text-muted">{t('portal.home.budgetCommitted')}</span>
          <span className="text-[15px] font-semibold">
            {data.budget.total_cents > 0
              ? t('portal.home.budgetOf', {
                  committed: formatMoney(data.budget.contracted_cents),
                  total: formatMoney(data.budget.total_cents),
                })
              : formatMoney(data.budget.contracted_cents)}
          </span>
        </span>
        <span aria-hidden="true">›</span>
      </Link>

      {data.team.length > 0 && (
        <p className="text-sm text-muted">
          {t('portal.home.yourPlanners', {
            names: data.team.map((m) => m.full_name).join(', '),
            organization: data.organization.name,
          })}
        </p>
      )}
    </div>
  );
}
