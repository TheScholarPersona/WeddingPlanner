import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Badge } from '@/components/Badge';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { api, ApiError, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

type Organization = Schemas['AdminOrganizationOut'];
type Created = Schemas['AdminOrganizationCreatedOut'];
const key = ['admin', 'organizations'];

export function AdminOrganizationsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const orgs = useQuery({
    queryKey: key,
    queryFn: () => api<Organization[]>('GET', '/admin/organizations'),
  });
  const status = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'suspend' | 'reactivate' }) =>
      api<Organization>('POST', `/admin/organizations/${id}/${action}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  if (orgs.isPending) return <Spinner />;
  if (orgs.error instanceof ApiError && orgs.error.code === 'two_factor_required') {
    return (
      <FormMessage>
        {t('admin.needs2fa')}{' '}
        <Link to="/admin/account" className="underline">
          {t('account.title')}
        </Link>
      </FormMessage>
    );
  }
  if (!orgs.data) return <FormMessage>{errorMessage(orgs.error, t)}</FormMessage>;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t('admin.organizations')} subtitle={t('admin.intro')} />
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-subtle text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">{t('admin.columns.name')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.columns.since')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.columns.team')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.columns.couples')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.columns.status')}</th>
              <th className="px-4 py-2.5 font-medium">
                <span className="sr-only">{t('admin.columns.actions')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {orgs.data.map((org) => (
              <tr key={org.id} className="border-t border-line-soft">
                <td className="px-4 py-3 font-medium">{org.name}</td>
                <td className="px-4 py-3 text-muted">{formatDate(org.created_at)}</td>
                <td className="px-4 py-3">{org.members}</td>
                <td className="px-4 py-3">{org.clients}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge tone={org.status === 'active' ? 'accent' : 'danger'}>
                      {t(`admin.status.${org.status}`)}
                    </Badge>
                    {org.support_until && (
                      <Badge tone="warning">
                        {t('admin.supportUntil', { date: formatDate(org.support_until) })}
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {org.support_until && (
                    <Button asChild variant="secondary" size="sm" className="mr-2">
                      <Link to={`/admin/organizations/${org.id}`}>{t('admin.openSupport')}</Link>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={status.isPending}
                    onClick={() => {
                      const action = org.status === 'active' ? 'suspend' : 'reactivate';
                      if (
                        action === 'reactivate' ||
                        window.confirm(t('admin.confirmSuspend', { name: org.name }))
                      ) {
                        status.mutate({ id: org.id, action });
                      }
                    }}
                  >
                    {org.status === 'active' ? t('admin.suspend') : t('admin.reactivate')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {status.error && <FormMessage>{errorMessage(status.error, t)}</FormMessage>}
      <div className="flex flex-wrap items-start gap-6">
        <CreateOrganization />
        <ResetTwoFactor />
      </div>
    </div>
  );
}

function CreateOrganization() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const create = useMutation({
    mutationFn: () =>
      api<Created>('POST', '/admin/organizations', { name: name.trim(), admin_email: email }),
    onSuccess: () => {
      setName('');
      setEmail('');
      void queryClient.invalidateQueries({ queryKey: key });
    },
  });
  return (
    <Card className="flex min-w-0 flex-[1_1_320px] flex-col gap-4">
      <CardTitle>{t('admin.create.title')}</CardTitle>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field id="org-name" label={t('admin.create.name')}>
          <Input id="org-name" required value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field id="org-email" label={t('admin.create.adminEmail')} hint={t('admin.create.hint')}>
          <Input
            id="org-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        {create.data && (
          <FormMessage tone="success">
            {t('admin.create.done', { name: create.data.organization.name })}
          </FormMessage>
        )}
        {create.error && <FormMessage>{errorMessage(create.error, t)}</FormMessage>}
        <div>
          <Button type="submit" disabled={create.isPending}>
            {t('admin.create.submit')}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ResetTwoFactor() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [reason, setReason] = useState('');
  const reset = useMutation({
    mutationFn: () => api('POST', '/admin/users/reset-2fa', { email, reason: reason.trim() }),
    onSuccess: () => {
      setEmail('');
      setReason('');
    },
  });
  return (
    <Card className="flex min-w-0 flex-[1_1_320px] flex-col gap-4">
      <CardTitle>{t('admin.reset2fa.title')}</CardTitle>
      <p className="text-sm text-ink-soft">{t('admin.reset2fa.intro')}</p>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (window.confirm(t('admin.reset2fa.confirm', { email }))) reset.mutate();
        }}
      >
        <Field id="reset-email" label={t('auth.fields.email')}>
          <Input
            id="reset-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field id="reset-reason" label={t('admin.reset2fa.reason')}>
          <Input
            id="reset-reason"
            required
            minLength={5}
            maxLength={300}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        {reset.isSuccess && <FormMessage tone="success">{t('admin.reset2fa.done')}</FormMessage>}
        {reset.error && <FormMessage>{errorMessage(reset.error, t)}</FormMessage>}
        <div>
          <Button type="submit" variant="secondary" disabled={reset.isPending}>
            {t('admin.reset2fa.submit')}
          </Button>
        </div>
      </form>
    </Card>
  );
}
