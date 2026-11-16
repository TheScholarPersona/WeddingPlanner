import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { Badge } from '@/components/Badge';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Card, CardTitle } from '@/components/ui/card';
import { api, type Schemas } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { formatDate, formatTime } from '@/lib/format';

type View = Schemas['SupportViewOut'];

/** Read-only look into an organization during an active support grant. */
export function AdminSupportPage() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const view = useQuery({
    queryKey: ['admin', 'support', id],
    queryFn: () => api<View>('GET', `/admin/organizations/${id}/support`),
    staleTime: 0,
  });
  if (view.isPending) return <Spinner />;
  if (!view.data) return <FormMessage>{errorMessage(view.error, t)}</FormMessage>;
  const data = view.data;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/admin">{t('admin.organizations')}</Link>}
        title={data.organization.name}
        subtitle={
          <Badge tone="warning">
            {t('admin.support.readOnlyUntil', { date: formatDate(data.grant_expires_at) })}
          </Badge>
        }
      />
      <p className="text-sm text-ink-soft">{t('admin.support.logged')}</p>
      <Card className="flex flex-col gap-2">
        <CardTitle>{t('admin.support.members')}</CardTitle>
        <ul>
          {data.members.map((m) => (
            <li
              key={m.email}
              className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft py-2.5 text-sm"
            >
              <span>
                <span className="font-medium">{m.full_name}</span>{' '}
                <span className="text-muted">· {m.email}</span>
              </span>
              <span className="flex gap-1.5">
                <Badge>{t(`roles.${m.role}` as never)}</Badge>
                {m.status !== 'active' && <Badge tone="danger">{m.status}</Badge>}
                <Badge tone={m.two_factor_enabled ? 'accent' : 'neutral'}>
                  {m.two_factor_enabled ? '2FA' : t('admin.support.no2fa')}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="flex flex-col gap-2">
        <CardTitle>{t('admin.support.weddings')}</CardTitle>
        {data.weddings.length === 0 && <p className="text-sm text-muted">—</p>}
        <ul>
          {data.weddings.map((w) => (
            <li
              key={w.id}
              className="flex flex-wrap justify-between gap-2 border-t border-line-soft py-2.5 text-sm"
            >
              <span className="font-medium">{w.title}</span>
              <span className="text-muted">
                {[w.wedding_date ? formatDate(w.wedding_date) : null, w.status, `${w.team} team`]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="flex flex-col gap-2">
        <CardTitle>{t('settings.auditLog')}</CardTitle>
        <ul>
          {data.audit.map((a, i) => (
            <li
              key={`${a.created_at}-${i}`}
              className="flex flex-wrap justify-between gap-2 border-t border-line-soft py-2 text-xs"
            >
              <span className="font-mono">{a.action}</span>
              <span className="text-muted">
                {a.actor_name ?? a.actor_type} · {formatDate(a.created_at)}{' '}
                {formatTime(a.created_at)}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
