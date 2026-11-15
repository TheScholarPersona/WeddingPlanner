import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';

import { portalKeys, portalPath, usePortalProject, type PortalBudget } from './api';

export function PortalBudgetPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  const budget = useQuery({
    queryKey: portalKeys.budget(project?.id ?? ''),
    queryFn: () => api<PortalBudget>('GET', `${portalPath(project!.id)}/budget`),
    enabled: !!project,
  });

  if (isPending || budget.isPending) return <Spinner />;
  if (!project || !budget.data) return <FormMessage>{errorMessage(budget.error, t)}</FormMessage>;
  const data = budget.data;
  const base = Math.max(data.total_cents, data.forecast_cents, 1);
  const pct = (cents: number) => `${Math.min(100, (cents * 100) / base)}%`;
  const stillToPay = Math.max(data.contracted_cents - data.paid_cents, 0);

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-4xl font-medium">{t('portal.budget.title')}</h1>
      <section className="flex flex-col gap-3.5 rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-col gap-0.5">
          <span className="text-sm text-muted">{t('portal.budget.committed')}</span>
          <span className="font-display text-[34px] leading-tight font-semibold">
            {formatMoney(data.contracted_cents)}{' '}
            {data.total_cents > 0 && (
              <span className="font-sans text-sm font-normal text-muted">
                {t('portal.budget.of', { total: formatMoney(data.total_cents) })}
              </span>
            )}
          </span>
        </div>
        <div
          role="img"
          aria-label={t('portal.budget.barLabel', {
            paid: formatMoney(data.paid_cents),
            open: formatMoney(stillToPay),
          })}
          className="flex h-2.5 overflow-hidden rounded-full bg-line"
        >
          <div className="bg-accent-strong" style={{ width: pct(data.paid_cents) }} />
          <div className="bg-accent" style={{ width: pct(stillToPay) }} />
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <span className="flex flex-col">
            <span className="text-muted">{t('portal.budget.paid')}</span>
            <span className="font-semibold">{formatMoney(data.paid_cents)}</span>
          </span>
          <span className="flex flex-col">
            <span className="text-muted">{t('portal.budget.stillToPay')}</span>
            <span className="font-semibold">{formatMoney(stillToPay)}</span>
          </span>
        </div>
      </section>

      {data.upcoming_payments.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">
            {t('portal.budget.nextPayments')}
          </h2>
          <ul className="flex flex-col gap-2">
            {data.upcoming_payments.map((payment) => (
              <li
                key={payment.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3.5"
              >
                <span className="flex flex-col gap-0.5">
                  <span className="text-[15px] font-medium">
                    {payment.item_title}, {payment.label}
                  </span>
                  <span className={cn('text-xs', payment.overdue ? 'text-danger' : 'text-muted')}>
                    {payment.due_date
                      ? t('portal.due', { date: formatDate(payment.due_date) })
                      : t('tasks.noDueDate')}
                  </span>
                </span>
                <span className="text-[15px] font-semibold">
                  {formatMoney(payment.amount_cents)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-muted uppercase">
          {t('portal.budget.byCategory')}
        </h2>
        {data.categories.length === 0 ? (
          <p className="text-sm text-muted">{t('portal.budget.empty')}</p>
        ) : (
          <div className="flex flex-col rounded-xl border border-line bg-surface px-4 py-1">
            {data.categories.flatMap((category) =>
              category.items.map((item) => (
                <div
                  key={item.id}
                  className="flex justify-between gap-3 border-b border-line-soft py-3 text-sm last:border-b-0"
                >
                  <span className="flex flex-col">
                    <span>{item.title}</span>
                    <span className="text-xs text-muted">{category.name}</span>
                  </span>
                  <span className="text-right text-ink-soft">
                    {formatMoney(item.contracted_cents ?? item.quoted_cents ?? item.planned_cents)}
                    <span
                      className={cn(
                        'block text-xs',
                        item.stage === 'booked' ? 'font-medium text-accent' : 'text-muted',
                      )}
                    >
                      {t(`portal.budget.stage.${item.stage}`)}
                    </span>
                  </span>
                </div>
              )),
            )}
          </div>
        )}
      </section>
    </div>
  );
}
