import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';

import { keys, type WeddingSummary } from './api';
import { WeddingRow } from './WeddingRow';

type View = 'all' | 'mine' | 'archived';

export function WeddingsPage() {
  const { t } = useTranslation();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const [view, setView] = useState<View>('all');
  const params =
    view === 'archived' ? 'status=archived' : view === 'mine' ? 'scope=mine' : 'scope=all';
  const weddings = useQuery({
    queryKey: keys.weddings(org, params),
    queryFn: () => api<WeddingSummary[]>('GET', `/orgs/${org}/projects?${params}`),
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t('weddings.title')}
        actions={
          <Button asChild>
            <Link to="/app/weddings/new">{t('weddings.new')}</Link>
          </Button>
        }
      />
      <div role="group" aria-label={t('weddings.filter')} className="flex flex-wrap gap-2">
        {(['all', 'mine', 'archived'] as const).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={view === option}
            onClick={() => setView(option)}
            className={cn(
              'h-9 rounded-full border px-4 text-sm',
              view === option
                ? 'border-accent bg-accent-soft font-semibold text-ink'
                : 'border-line bg-surface text-ink-soft',
            )}
          >
            {t(`weddings.views.${option}`)}
          </button>
        ))}
      </div>
      {weddings.isPending ? (
        <Spinner />
      ) : weddings.data?.length ? (
        <Card className="py-2">
          {weddings.data.map((wedding) => (
            <WeddingRow key={wedding.id} wedding={wedding} />
          ))}
        </Card>
      ) : (
        <EmptyState title={t('weddings.emptyTitle')} body={t('weddings.emptyBody')} />
      )}
    </div>
  );
}
