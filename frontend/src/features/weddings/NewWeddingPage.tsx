import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { keys, type Client, type Template, type Wedding } from './api';

const NEW_CLIENT = '__new__';

export function NewWeddingPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();

  const clients = useQuery({
    queryKey: keys.clients(org),
    queryFn: () => api<Client[]>('GET', `/orgs/${org}/clients`),
  });
  const templates = useQuery({
    queryKey: keys.templates(org),
    queryFn: () => api<Template[]>('GET', `/orgs/${org}/templates`),
  });

  const [clientChoice, setClientChoice] = useState(params.get('client') ?? NEW_CLIENT);
  const [form, setForm] = useState({
    newClientName: '',
    title: '',
    weddingDate: '',
    venueName: '',
    venueAddress: '',
    guests: '',
    templateId: '',
  });
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const defaultTemplate = templates.data?.find((tpl) => tpl.is_default);

  const create = useMutation({
    mutationFn: () =>
      api<Wedding>('POST', `/orgs/${org}/projects`, {
        client_id: clientChoice === NEW_CLIENT ? null : clientChoice,
        new_client_name: clientChoice === NEW_CLIENT ? form.newClientName : null,
        title: form.title || null,
        wedding_date: form.weddingDate || null,
        venue_name: form.venueName || null,
        venue_address: form.venueAddress || null,
        guest_count_planned: form.guests ? Number(form.guests) : null,
        template_id: form.templateId || defaultTemplate?.id || null,
      }),
    onSuccess: async (wedding) => {
      await queryClient.invalidateQueries({ queryKey: ['org', org] });
      void navigate(`/app/weddings/${wedding.id}`);
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/app/weddings">{t('weddings.title')}</Link>}
        title={t('weddings.new')}
        subtitle={t('weddings.newSubtitle')}
      />
      <Card>
        <form onSubmit={handleSubmit} className="grid gap-5 md:grid-cols-2">
          <Field id="client" label={t('weddings.fields.client')} className="md:col-span-2">
            <Select
              id="client"
              value={clientChoice}
              onChange={(e) => setClientChoice(e.target.value)}
            >
              <option value={NEW_CLIENT}>{t('weddings.fields.newClient')}</option>
              {clients.data?.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.display_name}
                </option>
              ))}
            </Select>
          </Field>
          {clientChoice === NEW_CLIENT && (
            <Field
              id="new-client"
              label={t('weddings.fields.coupleName')}
              hint={t('weddings.fields.coupleNameHint')}
              className="md:col-span-2"
            >
              <Input
                id="new-client"
                required
                value={form.newClientName}
                onChange={(e) => set('newClientName')(e.target.value)}
              />
            </Field>
          )}
          <Field id="wedding-date" label={t('weddings.fields.weddingDate')}>
            <Input
              id="wedding-date"
              type="date"
              value={form.weddingDate}
              onChange={(e) => set('weddingDate')(e.target.value)}
            />
          </Field>
          <Field id="guests" label={t('weddings.fields.guests')}>
            <Input
              id="guests"
              type="number"
              min={0}
              value={form.guests}
              onChange={(e) => set('guests')(e.target.value)}
            />
          </Field>
          <Field id="venue" label={t('weddings.fields.venue')}>
            <Input
              id="venue"
              value={form.venueName}
              onChange={(e) => set('venueName')(e.target.value)}
            />
          </Field>
          <Field id="venue-address" label={t('weddings.fields.venueAddress')}>
            <Input
              id="venue-address"
              value={form.venueAddress}
              onChange={(e) => set('venueAddress')(e.target.value)}
            />
          </Field>
          <Field
            id="title"
            label={t('weddings.fields.title')}
            hint={t('weddings.fields.titleHint')}
          >
            <Input id="title" value={form.title} onChange={(e) => set('title')(e.target.value)} />
          </Field>
          <Field
            id="template"
            label={t('weddings.fields.template')}
            hint={t('weddings.fields.templateHint')}
          >
            <Select
              id="template"
              value={form.templateId || defaultTemplate?.id || ''}
              onChange={(e) => set('templateId')(e.target.value)}
            >
              {templates.data?.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                </option>
              ))}
            </Select>
          </Field>
          {create.isError && (
            <div className="md:col-span-2">
              <FormMessage>{errorMessage(create.error, t)}</FormMessage>
            </div>
          )}
          <div className="flex gap-3 md:col-span-2">
            <Button type="submit" disabled={create.isPending}>
              {t('weddings.create')}
            </Button>
            <Button type="button" variant="secondary" asChild>
              <Link to="/app/weddings">{t('common.cancel')}</Link>
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
