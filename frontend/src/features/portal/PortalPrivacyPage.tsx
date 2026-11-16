import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { Spinner } from '@/components/Spinner';
import { Card } from '@/components/ui/card';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate } from '@/lib/format';

import { portalPath, usePortalProject } from './api';

type Consent = Schemas['ConsentOut'];

/** The couple's privacy choices: optional consents, each can be changed at any time. */
export function PortalPrivacyPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  if (isPending) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  return <Consents projectId={project.id} organization={project.organization.name} />;
}

function Consents({ projectId, organization }: { projectId: string; organization: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const path = `${portalPath(projectId)}/consents`;
  const key = ['portal', projectId, 'consents'];
  const consents = useQuery({ queryKey: key, queryFn: () => api<Consent[]>('GET', path) });
  const decide = useMutation({
    mutationFn: (body: { kind: string; granted: boolean }) => api<Consent[]>('PUT', path, body),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });

  if (consents.isPending) return <Spinner />;
  if (!consents.data) return <FormMessage>{errorMessage(consents.error, t)}</FormMessage>;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-4xl font-medium">{t('privacy.title')}</h1>
      <p className="text-sm text-ink-soft">{t('privacy.portalIntro', { organization })}</p>
      {consents.data.map((c) => (
        <Card key={c.kind} className="flex flex-col gap-3 p-5">
          <h2 className="text-base font-semibold">{t(`privacy.consents.kinds.${c.kind}.title`)}</h2>
          <p className="text-sm text-ink-soft">
            {t(`privacy.consents.kinds.${c.kind}.body`, { organization })}
          </p>
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">{t(`privacy.consents.kinds.${c.kind}.title`)}</legend>
            {[true, false].map((value) => (
              <label
                key={String(value)}
                className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-line px-4 text-sm has-[:checked]:border-accent has-[:checked]:bg-accent-soft"
              >
                <input
                  type="radio"
                  name={c.kind}
                  className="accent-accent"
                  checked={c.granted === value}
                  disabled={decide.isPending}
                  onChange={() => decide.mutate({ kind: c.kind, granted: value })}
                />
                {value ? t('privacy.consents.allow') : t('privacy.consents.deny')}
              </label>
            ))}
          </fieldset>
          {c.decided_at && (
            <p className="text-xs text-muted">
              {t('privacy.consents.decidedOn', { date: formatDate(c.decided_at) })}
            </p>
          )}
        </Card>
      ))}
      {decide.error && <FormMessage>{errorMessage(decide.error, t)}</FormMessage>}
      <p className="text-xs text-muted">
        {t('privacy.portalFootnote')}{' '}
        <Link to="/portal/account" className="font-medium text-accent">
          {t('account.title')}
        </Link>
      </p>
    </div>
  );
}
