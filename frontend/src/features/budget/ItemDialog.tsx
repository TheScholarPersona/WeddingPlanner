import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/Badge';
import { Dialog } from '@/components/Dialog';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatMoney } from '@/lib/format';

import {
  budgetKey,
  budgetPath,
  toCents,
  toInput,
  type BudgetCategory,
  type BudgetItem,
  type BudgetView,
} from './api';
import { MoneyInput } from './MoneyInput';

export function ItemDialog({
  org,
  projectId,
  item,
  categories,
  vendors,
  canEdit,
  onClose,
}: {
  org: string;
  projectId: string;
  item: BudgetItem;
  categories: BudgetCategory[];
  vendors: { id: string; name: string }[];
  canEdit: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const base = budgetPath(org, projectId);
  const [form, setForm] = useState({
    title: item.title,
    category_id: item.category_id,
    vendor_id: item.vendor_id ?? '',
    planned: toInput(item.planned_cents),
    quoted: toInput(item.quoted_cents),
    contracted: toInput(item.contracted_cents),
    internal: toInput(item.internal_cost_cents),
    visibility: item.visibility,
    notes: item.notes_internal ?? '',
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const update = (view: BudgetView) => {
    queryClient.setQueryData(budgetKey(org, projectId), view);
    void queryClient.invalidateQueries({ queryKey: ['org', org, 'dashboard'] });
  };

  const save = useMutation({
    mutationFn: () =>
      api<BudgetView>(
        'PATCH',
        `${base}/items/${item.id}`,
        {
          title: form.title,
          category_id: form.category_id,
          vendor_id: form.vendor_id || null,
          planned_cents: toCents(form.planned) ?? 0,
          quoted_cents: toCents(form.quoted),
          contracted_cents: toCents(form.contracted),
          internal_cost_cents: toCents(form.internal),
          visibility: form.visibility,
          notes_internal: form.notes || null,
        },
        { 'If-Match': `"${item.version}"` },
      ),
    onSuccess: (view) => {
      update(view);
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', `${base}/items/${item.id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: budgetKey(org, projectId) });
      onClose();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Dialog title={item.title} onClose={onClose}>
      <div className="flex max-h-[75vh] flex-col gap-6 overflow-y-auto pr-1">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
            <Field id="item-title" label={t('budget.fields.title')} className="sm:col-span-2">
              <Input
                id="item-title"
                required
                value={form.title}
                onChange={(e) => set('title')(e.target.value)}
              />
            </Field>
            <Field id="item-category" label={t('budget.fields.category')}>
              <Select
                id="item-category"
                value={form.category_id}
                onChange={(e) => set('category_id')(e.target.value)}
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="item-vendor" label={t('budget.fields.vendor')}>
              <Select
                id="item-vendor"
                value={form.vendor_id}
                onChange={(e) => set('vendor_id')(e.target.value)}
              >
                <option value="">{t('budget.noVendor')}</option>
                {vendors.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="item-planned" label={t('budget.columns.planned')}>
              <MoneyInput
                id="item-planned"
                value={form.planned}
                onChange={(e) => set('planned')(e.target.value)}
              />
            </Field>
            <Field id="item-quoted" label={t('budget.columns.quoted')}>
              <MoneyInput
                id="item-quoted"
                value={form.quoted}
                onChange={(e) => set('quoted')(e.target.value)}
              />
            </Field>
            <Field id="item-contracted" label={t('budget.columns.contracted')}>
              <MoneyInput
                id="item-contracted"
                value={form.contracted}
                onChange={(e) => set('contracted')(e.target.value)}
              />
            </Field>
            <Field
              id="item-internal"
              label={t('budget.columns.internalCost')}
              hint={t('weddings.internalOnly')}
            >
              <MoneyInput
                id="item-internal"
                value={form.internal}
                onChange={(e) => set('internal')(e.target.value)}
              />
            </Field>
            <Field
              id="item-visibility"
              label={t('tasks.fields.visibility')}
              hint={t('budget.visibilityHint')}
              className="sm:col-span-2"
            >
              <Select
                id="item-visibility"
                value={form.visibility}
                onChange={(e) => set('visibility')(e.target.value)}
              >
                <option value="internal">{t('tasks.internal')}</option>
                <option value="client">{t('tasks.shared')}</option>
              </Select>
            </Field>
            <Field
              id="item-notes"
              label={t('weddings.fields.internalNotes')}
              hint={t('weddings.internalOnly')}
              className="sm:col-span-2"
            >
              <Textarea
                id="item-notes"
                value={form.notes}
                onChange={(e) => set('notes')(e.target.value)}
              />
            </Field>
          </fieldset>
          {(save.isError || remove.isError) && (
            <FormMessage>{errorMessage(save.error ?? remove.error, t)}</FormMessage>
          )}
          {canEdit && (
            <div className="flex flex-wrap justify-between gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t('budget.confirmDelete', { title: item.title }))) {
                    remove.mutate();
                  }
                }}
              >
                {t('common.delete')}
              </Button>
              <Button type="submit" disabled={save.isPending}>
                {t('common.save')}
              </Button>
            </div>
          )}
        </form>
        <Payments org={org} projectId={projectId} item={item} canEdit={canEdit} onChange={update} />
      </div>
    </Dialog>
  );
}

function Payments({
  org,
  projectId,
  item,
  canEdit,
  onChange,
}: {
  org: string;
  projectId: string;
  item: BudgetItem;
  canEdit: boolean;
  onChange: (view: BudgetView) => void;
}) {
  const { t } = useTranslation();
  const base = `${budgetPath(org, projectId)}/items/${item.id}/payments`;
  const [form, setForm] = useState({ label: '', amount: '', due: '' });
  const add = useMutation({
    mutationFn: () =>
      api<BudgetView>('POST', base, {
        label: form.label,
        amount_cents: toCents(form.amount),
        due_date: form.due || null,
      }),
    onSuccess: (view) => {
      setForm({ label: '', amount: '', due: '' });
      onChange(view);
    },
  });
  const markPaid = useMutation({
    mutationFn: ({ id, paid }: { id: string; paid: boolean }) =>
      api<BudgetView>('PATCH', `${base}/${id}`, { paid }),
    onSuccess: onChange,
  });

  return (
    <section className="flex flex-col gap-3 border-t border-line pt-4">
      <h3 className="text-sm font-semibold">{t('budget.payments')}</h3>
      {item.payments.length === 0 && <p className="text-sm text-muted">{t('budget.noPayments')}</p>}
      <ul className="flex flex-col">
        {item.payments.map((payment) => (
          <li
            key={payment.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft py-2 text-sm last:border-b-0"
          >
            <span className="flex flex-col">
              <span className="font-medium">
                {payment.label} · {formatMoney(payment.amount_cents)}
              </span>
              <span className="text-xs text-muted">
                {payment.due_date
                  ? t('budget.dueOn', { date: formatDate(payment.due_date) })
                  : t('tasks.noDueDate')}
              </span>
            </span>
            {canEdit ? (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-accent"
                  checked={payment.paid_at != null}
                  onChange={(e) => markPaid.mutate({ id: payment.id, paid: e.target.checked })}
                />
                {t('budget.paid')}
              </label>
            ) : (
              payment.paid_at && <Badge tone="accent">{t('budget.paid')}</Badge>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Input
            aria-label={t('budget.paymentLabel')}
            placeholder={t('budget.paymentLabel')}
            required
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
          />
          <MoneyInput
            aria-label={t('budget.paymentAmount')}
            required
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
          <Input
            aria-label={t('budget.paymentDue')}
            type="date"
            value={form.due}
            onChange={(e) => setForm({ ...form, due: e.target.value })}
          />
          <Button type="submit" size="sm" className="h-11" disabled={add.isPending}>
            {t('common.add')}
          </Button>
        </form>
      )}
      {(add.error ?? markPaid.error) && (
        <FormMessage>{errorMessage(add.error ?? markPaid.error, t)}</FormMessage>
      )}
    </section>
  );
}
