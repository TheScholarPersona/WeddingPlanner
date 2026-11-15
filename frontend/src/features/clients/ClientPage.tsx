import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { keys } from '@/features/weddings/api';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import { CLIENT_STATUSES, statusTone } from './status';

type ClientDetail = Schemas['ClientDetailOut'];

export function ClientPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const { membership, isAdmin } = useActiveOrg();
  const org = membership.organization_id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const client = useQuery({
    queryKey: keys.client(org, id),
    queryFn: () => api<ClientDetail>('GET', `/orgs/${org}/clients/${id}`),
  });
  const remove = useMutation({
    mutationFn: () => api('DELETE', `/orgs/${org}/clients/${id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['org', org, 'clients'] });
      void navigate('/app/clients');
    },
  });

  if (client.isPending) return <Spinner />;
  if (!client.data) return <FormMessage>{errorMessage(client.error, t)}</FormMessage>;
  const data = client.data;

  return (
    <div className="flex flex-col gap-7">
      <PageHeader
        eyebrow={<Link to="/app/clients">{t('clients.title')}</Link>}
        title={data.display_name}
        subtitle={
          <Badge tone={statusTone(data.status)}>{t(`clients.status.${data.status}`)}</Badge>
        }
        actions={
          <>
            <Button asChild>
              <Link to={`/app/weddings/new?client=${data.id}`}>{t('weddings.new')}</Link>
            </Button>
            {isAdmin && (
              <Button
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t('clients.confirmDelete', { name: data.display_name }))) {
                    remove.mutate();
                  }
                }}
              >
                {t('common.delete')}
              </Button>
            )}
          </>
        }
      />
      {remove.isError && <FormMessage>{errorMessage(remove.error, t)}</FormMessage>}
      <div className="flex flex-wrap items-start gap-6">
        <ClientDetailsForm key={data.id} client={data} org={org} />
        <div className="flex min-w-0 flex-[2_1_320px] flex-col gap-6">
          <Contacts client={data} org={org} />
          <Card className="flex flex-col gap-2">
            <CardTitle>{t('clients.weddings')}</CardTitle>
            {data.projects.length === 0 && (
              <p className="text-sm text-muted">{t('clients.noWeddings')}</p>
            )}
            <ul>
              {data.projects.map((project) => (
                <li key={project.id} className="border-b border-line-soft py-2.5 last:border-b-0">
                  <Link to={`/app/weddings/${project.id}`} className="text-sm font-medium text-ink">
                    {project.title}
                  </Link>
                  <span className="block text-xs text-muted">
                    {project.wedding_date
                      ? formatDate(project.wedding_date)
                      : t('weddings.noDateYet')}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ClientDetailsForm({ client, org }: { client: ClientDetail; org: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    display_name: client.display_name,
    status: client.status,
    source: client.source ?? '',
    notes_internal: client.notes_internal ?? '',
  });
  const save = useMutation({
    mutationFn: () =>
      api<ClientDetail>('PATCH', `/orgs/${org}/clients/${client.id}`, {
        display_name: form.display_name,
        status: form.status,
        source: form.source || null,
        notes_internal: form.notes_internal || null,
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(keys.client(org, client.id), updated);
      await queryClient.invalidateQueries({ queryKey: ['org', org, 'clients'] });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Card className="flex min-w-0 flex-[3_1_420px] flex-col gap-4">
      <CardTitle>{t('clients.details')}</CardTitle>
      <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
        <Field id="c-name" label={t('clients.fields.name')} className="sm:col-span-2">
          <Input
            id="c-name"
            required
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </Field>
        <Field id="c-status" label={t('clients.columns.status')}>
          <Select
            id="c-status"
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value as ClientDetail['status'] })}
          >
            {CLIENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`clients.status.${s}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="c-source" label={t('clients.fields.source')}>
          <Input
            id="c-source"
            value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
          />
        </Field>
        <Field
          id="c-notes"
          label={t('weddings.fields.internalNotes')}
          hint={t('weddings.internalOnly')}
          className="sm:col-span-2"
        >
          <Textarea
            id="c-notes"
            value={form.notes_internal}
            onChange={(e) => setForm({ ...form, notes_internal: e.target.value })}
          />
        </Field>
        {save.isError && (
          <div className="sm:col-span-2">
            <FormMessage>{errorMessage(save.error, t)}</FormMessage>
          </div>
        )}
        {save.isSuccess && (
          <div className="sm:col-span-2">
            <FormMessage tone="success">{t('settings.saved')}</FormMessage>
          </div>
        )}
        <div>
          <Button type="submit" disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Contacts({ client, org }: { client: ClientDetail; org: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '' });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.client(org, client.id) });
  const base = `/orgs/${org}/clients/${client.id}/contacts`;

  const add = useMutation({
    mutationFn: () =>
      api('POST', base, {
        first_name: form.first_name,
        last_name: form.last_name || null,
        email: form.email || null,
        phone: form.phone || null,
        is_primary: client.contacts.length === 0,
      }),
    onSuccess: async () => {
      setForm({ first_name: '', last_name: '', email: '', phone: '' });
      setAdding(false);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api('DELETE', `${base}/${id}`),
    onSuccess: refresh,
  });

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('clients.contacts')}</CardTitle>
      <ul className="flex flex-col">
        {client.contacts.map((contact) => (
          <li
            key={contact.id}
            className="flex items-start justify-between gap-2 border-b border-line-soft py-2.5 text-sm last:border-b-0"
          >
            <span className="flex flex-col">
              <span className="font-medium">
                {[contact.first_name, contact.last_name].filter(Boolean).join(' ')}
                {contact.is_primary && (
                  <span className="ml-2 text-xs text-muted">{t('clients.primary')}</span>
                )}
              </span>
              {contact.email && <span className="text-xs text-muted">{contact.email}</span>}
              {contact.phone && <span className="text-xs text-muted">{contact.phone}</span>}
            </span>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('clients.removeContact', { name: contact.first_name })}
              onClick={() => remove.mutate(contact.id)}
            >
              {t('common.remove')}
            </Button>
          </li>
        ))}
      </ul>
      {adding ? (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Field id="n-first" label={t('clients.fields.firstName')}>
            <Input
              id="n-first"
              required
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
          </Field>
          <Field id="n-last" label={t('clients.fields.lastName')}>
            <Input
              id="n-last"
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
          </Field>
          <Field id="n-email" label={t('auth.fields.email')}>
            <Input
              id="n-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field id="n-phone" label={t('clients.fields.phone')}>
            <Input
              id="n-phone"
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" size="sm" disabled={add.isPending}>
              {t('clients.addContact')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => setAdding(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : (
        <div>
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            {t('clients.addContact')}
          </Button>
        </div>
      )}
      {(add.error ?? remove.error) && (
        <FormMessage>{errorMessage(add.error ?? remove.error, t)}</FormMessage>
      )}
    </Card>
  );
}
