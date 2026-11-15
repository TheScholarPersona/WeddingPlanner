import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, weddingPath, type Vendor, type Wedding } from '@/features/weddings/api';
import { WeddingNav } from '@/features/weddings/WeddingNav';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';

import {
  budgetKey,
  budgetPath,
  toCents,
  toInput,
  type BudgetCategory,
  type BudgetItem,
  type BudgetView,
} from './api';
import { ItemDialog } from './ItemDialog';
import { MoneyInput } from './MoneyInput';

export function BudgetPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [openItemId, setOpenItemId] = useState<string | null>(null);

  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });
  const budget = useQuery({
    queryKey: budgetKey(org, id),
    queryFn: () => api<BudgetView>('GET', budgetPath(org, id)),
  });
  const vendors = useQuery({
    queryKey: keys.vendors(org),
    queryFn: () => api<Vendor[]>('GET', `/orgs/${org}/vendors`),
  });

  if (wedding.isPending || budget.isPending) return <Spinner />;
  if (!wedding.data || !budget.data) {
    return <FormMessage>{errorMessage(wedding.error ?? budget.error, t)}</FormMessage>;
  }
  const can = (perm: string) => wedding.data.permissions.includes(perm);
  const canEdit = can('budget:write');
  const view = budget.data;
  // Always show the latest version of the open item (e.g. after adding a payment).
  const openItem = view.categories.flatMap((c) => c.items).find((i) => i.id === openItemId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />

      <Summary org={org} projectId={id} view={view} canSetTotal={can('budget:set_total')} />

      {view.categories.map((category) => (
        <CategoryCard
          key={category.id}
          org={org}
          projectId={id}
          category={category}
          canEdit={canEdit}
          onOpen={(item) => setOpenItemId(item.id)}
        />
      ))}

      {canEdit && <NewCategoryForm org={org} projectId={id} />}

      {view.upcoming_payments.length > 0 && (
        <Card className="flex flex-col gap-2">
          <CardTitle>{t('budget.upcomingPayments')}</CardTitle>
          <ul>
            {view.upcoming_payments.map((payment) => (
              <li
                key={payment.id}
                className="flex flex-wrap justify-between gap-2 border-t border-line-soft py-2.5 text-sm"
              >
                <span>
                  <span
                    className={cn('text-muted', payment.overdue && 'font-semibold text-danger')}
                  >
                    {payment.due_date ? formatDate(payment.due_date) : t('tasks.noDueDate')} ·{' '}
                  </span>
                  {payment.item_title}, {payment.label}
                </span>
                <span className="font-semibold">{formatMoney(payment.amount_cents)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <p className="text-sm text-muted">{t('budget.footnote')}</p>

      {openItem && (
        <ItemDialog
          key={openItem.id}
          org={org}
          projectId={id}
          item={openItem}
          categories={view.categories}
          vendors={vendors.data ?? []}
          canEdit={canEdit}
          onClose={() => setOpenItemId(null)}
        />
      )}
    </div>
  );
}

function Summary({
  org,
  projectId,
  view,
  canSetTotal,
}: {
  org: string;
  projectId: string;
  view: BudgetView;
  canSetTotal: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [total, setTotal] = useState(toInput(view.total_cents));
  const save = useMutation({
    mutationFn: () =>
      api<BudgetView>(
        'PATCH',
        budgetPath(org, projectId),
        { total_cents: toCents(total) ?? 0 },
        { 'If-Match': `"${view.version}"` },
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(budgetKey(org, projectId), updated);
      setEditing(false);
    },
  });

  const { totals } = view;
  const base = Math.max(view.total_cents, totals.forecast_cents, 1);
  const pct = (cents: number) => `${Math.min(100, (cents * 100) / base)}%`;
  const committedUnpaid = Math.max(totals.contracted_cents - totals.paid_cents, 0);
  const plannedOnly = Math.max(totals.forecast_cents - totals.contracted_cents, 0);

  return (
    <Card className="flex flex-col gap-5">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-muted">{t('budget.total')}</span>
          {editing ? (
            <form
              className="flex gap-2"
              onSubmit={(e: FormEvent<HTMLFormElement>) => {
                e.preventDefault();
                save.mutate();
              }}
            >
              <MoneyInput
                aria-label={t('budget.total')}
                value={total}
                onChange={(e) => setTotal(e.target.value)}
              />
              <Button type="submit" size="sm" className="h-11" disabled={save.isPending}>
                {t('common.save')}
              </Button>
            </form>
          ) : (
            <span className="flex items-baseline gap-2">
              <span className="font-display text-[34px] leading-tight font-semibold">
                {formatMoney(view.total_cents)}
              </span>
              {canSetTotal && (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto px-0"
                  onClick={() => setEditing(true)}
                >
                  {t('common.edit')}
                </Button>
              )}
            </span>
          )}
        </div>
        {(
          [
            ['forecast', totals.forecast_cents],
            ['contracted', totals.contracted_cents],
            ['paid', totals.paid_cents],
          ] as const
        ).map(([key, cents]) => (
          <div key={key} className="flex flex-col gap-1">
            <span className="text-sm text-muted">{t(`budget.summary.${key}`)}</span>
            <span className="font-display text-[34px] leading-tight font-semibold">
              {formatMoney(cents)}
            </span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        <div
          role="img"
          aria-label={t('budget.barLabel', {
            paid: formatMoney(totals.paid_cents),
            contracted: formatMoney(totals.contracted_cents),
            forecast: formatMoney(totals.forecast_cents),
          })}
          className="flex h-3 overflow-hidden rounded-full bg-line"
        >
          <div className="bg-accent-strong" style={{ width: pct(totals.paid_cents) }} />
          <div className="bg-accent" style={{ width: pct(committedUnpaid) }} />
          <div className="bg-accent-tint" style={{ width: pct(plannedOnly) }} />
        </div>
        <div className="flex flex-wrap gap-5 text-xs text-ink-soft">
          <Legend className="bg-accent-strong" label={t('budget.legend.paid')} />
          <Legend className="bg-accent" label={t('budget.legend.contracted')} />
          <Legend className="bg-accent-tint" label={t('budget.legend.planned')} />
          {view.total_cents > 0 && (
            <span>
              {t('budget.legend.unplanned', { amount: formatMoney(totals.unplanned_cents) })}
            </span>
          )}
          <span>
            {t('budget.legend.internalCost', { amount: formatMoney(totals.internal_cost_cents) })}
          </span>
        </div>
      </div>
      {view.warnings.map((warning, index) => (
        <p
          key={`${warning.code}-${warning.item_id ?? index}`}
          role="status"
          className={cn(
            'rounded-lg px-4 py-3 text-sm',
            warning.code === 'over_budget' || warning.code === 'payment_overdue'
              ? 'bg-danger-soft text-danger'
              : 'bg-warning-soft text-warning',
          )}
        >
          {t(`budget.warnings.${warning.code}`, {
            amount: formatMoney(warning.amount_cents),
            title: warning.title ?? '',
          })}
        </p>
      ))}
      {save.isError && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
    </Card>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span aria-hidden="true" className={cn('size-2.5 rounded-sm', className)} />
      {label}
    </span>
  );
}

function CategoryCard({
  org,
  projectId,
  category,
  canEdit,
  onOpen,
}: {
  org: string;
  projectId: string;
  category: BudgetCategory;
  canEdit: boolean;
  onOpen: (item: BudgetItem) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [planned, setPlanned] = useState('');
  const add = useMutation({
    mutationFn: () =>
      api<BudgetView>('POST', `${budgetPath(org, projectId)}/items`, {
        category_id: category.id,
        title,
        planned_cents: toCents(planned) ?? 0,
      }),
    onSuccess: (view) => {
      setTitle('');
      setPlanned('');
      queryClient.setQueryData(budgetKey(org, projectId), view);
    },
  });
  const money = (cents: number | null) => (cents == null ? '–' : formatMoney(cents));

  return (
    <Card className="flex flex-col gap-2 overflow-x-auto py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-[22px] font-semibold">{category.name}</h2>
        <span className="text-sm text-muted">
          {t('budget.categoryTotal', {
            planned: formatMoney(category.planned_cents),
            forecast: formatMoney(category.forecast_cents),
          })}
        </span>
      </div>
      {category.items.length > 0 && (
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs tracking-wide text-muted uppercase">
            <tr>
              <th className="py-2 font-semibold">{t('budget.columns.item')}</th>
              <th className="py-2 text-right font-semibold">{t('budget.columns.planned')}</th>
              <th className="py-2 text-right font-semibold">{t('budget.columns.quoted')}</th>
              <th className="py-2 text-right font-semibold">{t('budget.columns.contracted')}</th>
              <th className="py-2 text-right font-semibold">{t('budget.columns.paid')}</th>
              <th className="py-2 text-right font-semibold">{t('budget.columns.internalCost')}</th>
              <th className="py-2 pl-4 font-semibold">{t('budget.columns.couple')}</th>
            </tr>
          </thead>
          <tbody>
            {category.items.map((item) => {
              const overQuote =
                item.quoted_cents != null &&
                item.planned_cents > 0 &&
                item.quoted_cents > item.planned_cents;
              return (
                <tr key={item.id} className="border-t border-line-soft">
                  <td className="py-2.5">
                    <button
                      type="button"
                      className="cursor-pointer text-left font-medium"
                      onClick={() => onOpen(item)}
                    >
                      {item.title}
                    </button>
                    {item.vendor_name && (
                      <span className="block text-xs text-muted">{item.vendor_name}</span>
                    )}
                  </td>
                  <td className="py-2.5 text-right">{money(item.planned_cents)}</td>
                  <td
                    className={cn('py-2.5 text-right', overQuote && 'font-semibold text-warning')}
                  >
                    {money(item.quoted_cents)}
                  </td>
                  <td className="py-2.5 text-right">{money(item.contracted_cents)}</td>
                  <td className="py-2.5 text-right">{money(item.paid_cents)}</td>
                  <td className="py-2.5 text-right text-muted">
                    {money(item.internal_cost_cents)}
                  </td>
                  <td className="py-2.5 pl-4">
                    <Badge tone={item.visibility === 'client' ? 'accent' : 'neutral'}>
                      {item.visibility === 'client' ? t('budget.visible') : t('tasks.internal')}
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {canEdit && (
        <form
          className="flex flex-wrap gap-2 pt-1"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Input
            aria-label={t('budget.newItemIn', { category: category.name })}
            placeholder={t('budget.newItem')}
            className="min-w-0 flex-[3_1_200px]"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex-[1_1_140px]">
            <MoneyInput
              aria-label={t('budget.plannedFor', { category: category.name })}
              placeholder={t('budget.columns.planned')}
              value={planned}
              onChange={(e) => setPlanned(e.target.value)}
            />
          </div>
          <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
            {t('common.add')}
          </Button>
        </form>
      )}
      {add.isError && <FormMessage>{errorMessage(add.error, t)}</FormMessage>}
    </Card>
  );
}

function NewCategoryForm({ org, projectId }: { org: string; projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const add = useMutation({
    mutationFn: () => api<BudgetView>('POST', `${budgetPath(org, projectId)}/categories`, { name }),
    onSuccess: (view) => {
      setName('');
      queryClient.setQueryData(budgetKey(org, projectId), view);
    },
  });
  return (
    <form
      className="flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <Input
        aria-label={t('budget.newCategory')}
        placeholder={t('budget.newCategory')}
        className="max-w-xs"
        required
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Button type="submit" variant="secondary" className="h-11" disabled={add.isPending}>
        {t('budget.addCategory')}
      </Button>
    </form>
  );
}
