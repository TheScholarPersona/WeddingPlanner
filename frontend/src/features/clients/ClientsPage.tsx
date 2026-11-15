import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';

import { Badge } from '@/components/Badge';
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
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys, type Client } from '@/features/weddings/api';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import { CLIENT_STATUSES, statusTone } from './status';

export function ClientsPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [creating, setCreating] = useState(false);
  const params = new URLSearchParams({ ...(status && { status }), ...(q && { q }) }).toString();
  const clients = useQuery({
    queryKey: keys.clients(org, params),
    queryFn: () => api<Client[]>('GET', `/orgs/${org}/clients${params ? `?${params}` : ''}`),
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t('clients.title')}
        subtitle={t('clients.subtitle')}
        actions={<Button onClick={() => setCreating(true)}>{t('clients.new')}</Button>}
      />
      <div className="flex flex-wrap gap-3">
        <Input
          type="search"
          aria-label={t('clients.search')}
          placeholder={t('clients.search')}
          className="max-w-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          aria-label={t('clients.filterStatus')}
          className="w-auto"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">{t('clients.allStatuses')}</option>
          {CLIENT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`clients.status.${s}`)}
            </option>
          ))}
        </Select>
      </div>
      {clients.isPending ? (
        <Spinner />
      ) : clients.data?.length ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-line text-xs tracking-wide text-muted uppercase">
              <tr>
                <th className="px-6 py-3 font-semibold">{t('clients.columns.name')}</th>
                <th className="px-6 py-3 font-semibold">{t('clients.columns.status')}</th>
                <th className="px-6 py-3 font-semibold">{t('clients.columns.contact')}</th>
                <th className="px-6 py-3 font-semibold">{t('clients.columns.nextWedding')}</th>
              </tr>
            </thead>
            <tbody>
              {clients.data.map((client) => (
                <tr key={client.id} className="border-b border-line-soft last:border-b-0">
                  <td className="px-6 py-3.5">
                    <Link to={`/app/clients/${client.id}`} className="font-semibold text-ink">
                      {client.display_name}
                    </Link>
                  </td>
                  <td className="px-6 py-3.5">
                    <Badge tone={statusTone(client.status)}>
                      {t(`clients.status.${client.status}`)}
                    </Badge>
                  </td>
                  <td className="px-6 py-3.5 text-ink-soft">
                    {client.primary_contact ?? '–'}
                    {client.primary_email && (
                      <span className="block text-xs text-muted">{client.primary_email}</span>
                    )}
                  </td>
                  <td className="px-6 py-3.5 text-ink-soft">
                    {client.next_wedding_date ? formatDate(client.next_wedding_date) : '–'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : (
        <EmptyState title={t('clients.emptyTitle')} body={t('clients.emptyBody')} />
      )}
      {creating && <NewClientDialog org={org} onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewClientDialog({ org, onClose }: { org: string; onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    display_name: '',
    status: 'inquiry',
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const create = useMutation({
    mutationFn: () =>
      api<Schemas['ClientDetailOut']>('POST', `/orgs/${org}/clients`, {
        display_name: form.display_name,
        status: form.status,
        contacts: form.first_name
          ? [
              {
                first_name: form.first_name,
                last_name: form.last_name || null,
                email: form.email || null,
                phone: form.phone || null,
              },
            ]
          : [],
      }),
    onSuccess: async (client) => {
      await queryClient.invalidateQueries({ queryKey: ['org', org, 'clients'] });
      void navigate(`/app/clients/${client.id}`);
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <Dialog title={t('clients.new')} onClose={onClose}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field
          id="client-name"
          label={t('clients.fields.name')}
          hint={t('clients.fields.nameHint')}
        >
          <Input
            id="client-name"
            required
            value={form.display_name}
            onChange={(e) => set('display_name')(e.target.value)}
          />
        </Field>
        <Field id="client-status" label={t('clients.columns.status')}>
          <Select
            id="client-status"
            value={form.status}
            onChange={(e) => set('status')(e.target.value)}
          >
            {CLIENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`clients.status.${s}`)}
              </option>
            ))}
          </Select>
        </Field>
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-2 text-sm font-semibold">{t('clients.primaryContact')}</legend>
          <Field id="contact-first" label={t('clients.fields.firstName')}>
            <Input
              id="contact-first"
              value={form.first_name}
              onChange={(e) => set('first_name')(e.target.value)}
            />
          </Field>
          <Field id="contact-last" label={t('clients.fields.lastName')}>
            <Input
              id="contact-last"
              value={form.last_name}
              onChange={(e) => set('last_name')(e.target.value)}
            />
          </Field>
          <Field id="contact-email" label={t('auth.fields.email')}>
            <Input
              id="contact-email"
              type="email"
              value={form.email}
              onChange={(e) => set('email')(e.target.value)}
            />
          </Field>
          <Field id="contact-phone" label={t('clients.fields.phone')}>
            <Input
              id="contact-phone"
              type="tel"
              value={form.phone}
              onChange={(e) => set('phone')(e.target.value)}
            />
          </Field>
        </fieldset>
        {create.isError && <FormMessage>{errorMessage(create.error, t)}</FormMessage>}
        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {t('clients.create')}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
