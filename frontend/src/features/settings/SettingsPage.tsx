import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { meQueryKey } from '@/features/auth/session';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { SupportAccessCard, TwoFactorPolicyCard } from './SecuritySettings';

type Organization = Schemas['OrganizationOut'];
type AuditPage = Schemas['AuditPageOut'];

const LOCALES = ['de-DE', 'de-AT', 'de-CH', 'en-GB', 'en-US'] as const;
const TIMEZONES = ['Europe/Berlin', 'Europe/Vienna', 'Europe/Zurich', 'Europe/London'] as const;

export function SettingsPage() {
  const { t } = useTranslation();
  const { membership, isAdmin } = useActiveOrg();
  const orgId = membership.organization_id;
  const org = useQuery({
    queryKey: ['org', orgId, 'details'],
    queryFn: () => api<Organization>('GET', `/orgs/${orgId}`),
  });

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-[44px] leading-tight font-medium">
          {t('settings.title')}
        </h1>
        <p className="text-sm text-muted">{t('settings.subtitle')}</p>
      </header>
      {org.data ? (
        <OrganizationForm key={org.data.id} org={org.data} editable={isAdmin} />
      ) : (
        <Spinner />
      )}
      {isAdmin && org.data && <TwoFactorPolicyCard org={org.data} />}
      {isAdmin && <SupportAccessCard orgId={orgId} />}
      {isAdmin && <AuditLog orgId={orgId} />}
    </div>
  );
}

function OrganizationForm({ org, editable }: { org: Organization; editable: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(org);

  const save = useMutation({
    mutationFn: () =>
      api<Organization>('PATCH', `/orgs/${org.id}`, {
        name: form.name,
        accent_color: form.accent_color || null,
        locale: form.locale,
        timezone: form.timezone,
        client_access_days_after_archive: form.client_access_days_after_archive,
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['org', org.id, 'details'], updated);
      await queryClient.invalidateQueries({ queryKey: meQueryKey });
      await queryClient.invalidateQueries({ queryKey: ['org', org.id, 'audit'] });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  const set = <K extends keyof Organization>(key: K, value: Organization[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <Card>
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <CardTitle>{t('settings.organization')}</CardTitle>
        <fieldset disabled={!editable} className="grid gap-5 md:grid-cols-2">
          <div className="flex flex-col gap-2 md:col-span-2">
            <Label htmlFor="org-name">{t('settings.fields.name')}</Label>
            <Input
              id="org-name"
              required
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="org-accent">{t('settings.fields.accentColor')}</Label>
            <div className="flex items-center gap-3">
              <input
                id="org-accent"
                type="color"
                className="h-11 w-16 cursor-pointer rounded-lg border border-line bg-surface"
                value={form.accent_color ?? '#4f6354'}
                onChange={(e) => set('accent_color', e.target.value)}
              />
              <span className="text-sm text-muted">
                {form.accent_color ?? t('settings.default')}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="org-access">{t('settings.fields.clientAccessDays')}</Label>
            <Input
              id="org-access"
              type="number"
              min={0}
              max={3650}
              value={form.client_access_days_after_archive}
              onChange={(e) => set('client_access_days_after_archive', Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="org-locale">{t('settings.fields.locale')}</Label>
            <select
              id="org-locale"
              className="h-11 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm"
              value={form.locale}
              onChange={(e) => set('locale', e.target.value)}
            >
              {LOCALES.map((locale) => (
                <option key={locale} value={locale}>
                  {t(`settings.locales.${locale}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="org-timezone">{t('settings.fields.timezone')}</Label>
            <select
              id="org-timezone"
              className="h-11 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm"
              value={form.timezone}
              onChange={(e) => set('timezone', e.target.value)}
            >
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </div>
        </fieldset>
        {save.isError && <FormMessage>{errorMessage(save.error, t)}</FormMessage>}
        {save.isSuccess && <FormMessage tone="success">{t('settings.saved')}</FormMessage>}
        {editable ? (
          <div>
            <Button type="submit" disabled={save.isPending}>
              {t('common.save')}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted">{t('settings.adminOnly')}</p>
        )}
      </form>
    </Card>
  );
}

function AuditLog({ orgId }: { orgId: string }) {
  const { t, i18n } = useTranslation();
  const log = useInfiniteQuery({
    queryKey: ['org', orgId, 'audit'],
    queryFn: ({ pageParam }) =>
      api<AuditPage>(
        'GET',
        `/orgs/${orgId}/audit-log?limit=25${pageParam ? `&cursor=${pageParam}` : ''}`,
      ),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const entries = log.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>{t('settings.auditLog')}</CardTitle>
      <p className="text-sm text-muted">{t('settings.auditLogHint')}</p>
      {log.isPending ? (
        <Spinner />
      ) : (
        <ul className="flex flex-col">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-wrap justify-between gap-2 border-t border-line-soft py-3 text-sm"
            >
              <span>
                <span className="font-medium">{entry.actor_name ?? t('settings.system')}</span>{' '}
                {i18n.exists(`audit.${entry.action}`)
                  ? t(`audit.${entry.action}` as never)
                  : entry.action}
              </span>
              <time className="text-muted" dateTime={entry.created_at}>
                {new Intl.DateTimeFormat('de-DE', {
                  dateStyle: 'short',
                  timeStyle: 'short',
                }).format(new Date(entry.created_at))}
              </time>
            </li>
          ))}
        </ul>
      )}
      {log.hasNextPage && (
        <div>
          <Button
            variant="secondary"
            size="sm"
            disabled={log.isFetchingNextPage}
            onClick={() => void log.fetchNextPage()}
          >
            {t('common.loadMore')}
          </Button>
        </div>
      )}
    </Card>
  );
}
