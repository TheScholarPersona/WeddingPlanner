import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { Badge } from '@/components/Badge';
import { Field } from '@/components/Field';
import { FormMessage } from '@/components/FormMessage';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { useReauth } from '@/features/team/useReauth';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

type Organization = Schemas['OrganizationOut'];
type Grant = Schemas['SupportGrantOut'];

/** Organization admins: require 2FA for the team. */
export function TwoFactorPolicyCard({ org }: { org: Organization }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (value: boolean) =>
      api<Organization>('PATCH', `/orgs/${org.id}`, { require_2fa: value }),
    onSuccess: (data) => queryClient.setQueryData(['org', org.id, 'details'], data),
  });
  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('settings.security.title')}</CardTitle>
      <div className="flex items-start justify-between gap-4">
        <label htmlFor="require-2fa" className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">{t('settings.security.require2fa')}</span>
          <span className="text-xs text-muted">{t('settings.security.require2faHint')}</span>
        </label>
        <input
          id="require-2fa"
          type="checkbox"
          role="switch"
          className="mt-1 size-5 shrink-0 accent-accent"
          checked={org.require_2fa}
          disabled={save.isPending}
          onChange={(e) => save.mutate(e.target.checked)}
        />
      </div>
      {save.error && (
        <FormMessage>
          {errorMessage(save.error, t)}{' '}
          <Link to="/app/account" className="underline">
            {t('settings.security.openAccount')}
          </Link>
        </FormMessage>
      )}
    </Card>
  );
}

/** Organization admins: let platform support look in for a few days (read-only). */
export function SupportAccessCard({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { run, dialog } = useReauth();
  const key = ['org', orgId, 'support-access'];
  const path = `/orgs/${orgId}/support-access`;
  const grants = useQuery({ queryKey: key, queryFn: () => api<Grant[]>('GET', path) });
  const [days, setDays] = useState('3');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<unknown>(null);
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: key }),
      queryClient.invalidateQueries({ queryKey: ['org', orgId, 'audit'] }),
    ]);
  const revoke = useMutation({
    mutationFn: (id: string) => api('DELETE', `${path}/${id}`),
    onSuccess: refresh,
  });
  const active = grants.data?.find((g) => g.active);

  const grant = () => {
    setError(null);
    void run(
      () => api<Grant>('POST', path, { days: Number(days), reason: reason.trim() || null }),
      () => {
        setReason('');
        void refresh();
      },
    ).catch(setError);
  };

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>{t('settings.support.title')}</CardTitle>
        {active && <Badge tone="warning">{t('settings.support.activeBadge')}</Badge>}
      </div>
      <p className="text-sm text-ink-soft">{t('settings.support.intro')}</p>
      {active ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-warning-soft p-3 text-sm">
          <span>
            {t('settings.support.activeUntil', { date: formatDate(active.expires_at) })}
            {active.reason ? ` · ${active.reason}` : ''}
          </span>
          <Button variant="secondary" size="sm" onClick={() => revoke.mutate(active.id)}>
            {t('settings.support.endNow')}
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Field id="support-days" label={t('settings.support.duration')} className="w-40">
            <Select id="support-days" value={days} onChange={(e) => setDays(e.target.value)}>
              {[1, 3, 7, 14].map((d) => (
                <option key={d} value={d}>
                  {t('settings.support.days', { count: d })}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="support-reason" label={t('settings.support.reason')} className="flex-1">
            <Input
              id="support-reason"
              maxLength={300}
              placeholder={t('settings.support.reasonPlaceholder')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <Button onClick={grant}>{t('settings.support.grant')}</Button>
        </div>
      )}
      {(error != null || revoke.error) && (
        <FormMessage>{errorMessage(error ?? revoke.error, t)}</FormMessage>
      )}
      {dialog}
    </Card>
  );
}
