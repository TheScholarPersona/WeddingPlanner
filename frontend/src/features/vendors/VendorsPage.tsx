import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '@/components/Dialog';
import { EmptyState } from '@/components/EmptyState';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, type Vendor } from '@/features/weddings/api';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { CATEGORIES } from './categories';

export function VendorsPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [category, setCategory] = useState('');
  const [editing, setEditing] = useState<Vendor | 'new' | null>(null);
  const vendors = useQuery({
    queryKey: keys.vendors(org),
    queryFn: () => api<Vendor[]>('GET', `/orgs/${org}/vendors`),
  });
  const shown = (vendors.data ?? []).filter((v) => !category || v.category === category);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t('vendors.title')}
        subtitle={t('vendors.subtitle')}
        actions={<Button onClick={() => setEditing('new')}>{t('vendors.new')}</Button>}
      />
      <Select
        aria-label={t('vendors.filterCategory')}
        className="w-auto max-w-xs"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      >
        <option value="">{t('vendors.allCategories')}</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {t(`vendors.categories.${c}`)}
          </option>
        ))}
      </Select>
      {vendors.isPending ? (
        <Spinner />
      ) : shown.length ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {shown.map((vendor) => (
            <Card key={vendor.id} className="flex flex-col gap-2 p-5">
              <span className="text-xs font-semibold tracking-wide text-muted uppercase">
                {t(`vendors.categories.${vendor.category}`)}
              </span>
              <span className="font-display text-2xl font-semibold">{vendor.name}</span>
              <span className="text-sm text-ink-soft">
                {[vendor.contact_name, vendor.email, vendor.phone].filter(Boolean).join(' · ') ||
                  t('vendors.noContact')}
              </span>
              <span className="text-xs text-muted">
                {t('vendors.usedIn', { count: vendor.project_count })}
                {vendor.rating ? ` · ${'★'.repeat(vendor.rating)}` : ''}
              </span>
              <div>
                <Button variant="secondary" size="sm" onClick={() => setEditing(vendor)}>
                  {t('common.edit')}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState title={t('vendors.emptyTitle')} body={t('vendors.emptyBody')} />
      )}
      {editing && (
        <VendorDialog
          org={org}
          vendor={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function VendorDialog({
  org,
  vendor,
  onClose,
}: {
  org: string;
  vendor: Vendor | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: vendor?.name ?? '',
    category: vendor?.category ?? 'venue',
    contact_name: vendor?.contact_name ?? '',
    email: vendor?.email ?? '',
    phone: vendor?.phone ?? '',
    website: vendor?.website ?? '',
    rating: vendor?.rating?.toString() ?? '',
    notes_internal: vendor?.notes_internal ?? '',
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const body = () => ({
    name: form.name,
    category: form.category,
    contact_name: form.contact_name || null,
    email: form.email || null,
    phone: form.phone || null,
    website: form.website || null,
    rating: form.rating ? Number(form.rating) : null,
    notes_internal: form.notes_internal || null,
  });
  const done = async () => {
    await queryClient.invalidateQueries({ queryKey: keys.vendors(org) });
    onClose();
  };
  const save = useMutation({
    mutationFn: () =>
      vendor
        ? api('PATCH', `/orgs/${org}/vendors/${vendor.id}`, body())
        : api('POST', `/orgs/${org}/vendors`, body()),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', `/orgs/${org}/vendors/${vendor?.id}`),
    onSuccess: done,
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Dialog title={vendor ? vendor.name : t('vendors.new')} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="v-name" label={t('vendors.fields.name')}>
            <Input
              id="v-name"
              required
              value={form.name}
              onChange={(e) => set('name')(e.target.value)}
            />
          </Field>
          <Field id="v-category" label={t('vendors.fields.category')}>
            <Select
              id="v-category"
              value={form.category}
              onChange={(e) => set('category')(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`vendors.categories.${c}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="v-contact" label={t('vendors.fields.contact')}>
            <Input
              id="v-contact"
              value={form.contact_name}
              onChange={(e) => set('contact_name')(e.target.value)}
            />
          </Field>
          <Field id="v-email" label={t('auth.fields.email')}>
            <Input
              id="v-email"
              type="email"
              value={form.email}
              onChange={(e) => set('email')(e.target.value)}
            />
          </Field>
          <Field id="v-phone" label={t('clients.fields.phone')}>
            <Input
              id="v-phone"
              type="tel"
              value={form.phone}
              onChange={(e) => set('phone')(e.target.value)}
            />
          </Field>
          <Field id="v-website" label={t('vendors.fields.website')}>
            <Input
              id="v-website"
              type="url"
              placeholder="https://"
              value={form.website}
              onChange={(e) => set('website')(e.target.value)}
            />
          </Field>
          <Field id="v-rating" label={t('vendors.fields.rating')}>
            <Select
              id="v-rating"
              value={form.rating}
              onChange={(e) => set('rating')(e.target.value)}
            >
              <option value="">{t('vendors.noRating')}</option>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {'★'.repeat(n)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field
          id="v-notes"
          label={t('weddings.fields.internalNotes')}
          hint={t('weddings.internalOnly')}
        >
          <Textarea
            id="v-notes"
            value={form.notes_internal}
            onChange={(e) => set('notes_internal')(e.target.value)}
          />
        </Field>
        {(save.isError || remove.isError) && (
          <FormMessage>{errorMessage(save.error ?? remove.error, t)}</FormMessage>
        )}
        <div className="flex flex-wrap justify-between gap-3">
          {vendor ? (
            <Button type="button" variant="ghost" onClick={() => remove.mutate()}>
              {t('common.delete')}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-3">
            <Button type="button" variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
