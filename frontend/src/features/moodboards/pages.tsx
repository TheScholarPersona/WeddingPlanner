import { useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { EmptyState } from '@/components/EmptyState';
import { FormMessage } from '@/components/FormMessage';
import { PageHeader } from '@/components/PageHeader';
import { Spinner } from '@/components/Spinner';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { usePortalProject } from '@/features/portal/api';
import { keys, weddingPath, type Wedding } from '@/features/weddings/api';
import { WeddingNav } from '@/features/weddings/WeddingNav';
import { api } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';

import { coupleScope, teamScope } from './api';
import { BoardList } from './BoardList';
import { BoardView } from './BoardView';

function useWedding() {
  const { id = '' } = useParams();
  const { membership } = useActiveOrg();
  const org = membership.organization_id;
  const wedding = useQuery({
    queryKey: keys.wedding(org, id),
    queryFn: () => api<Wedding>('GET', weddingPath(org, id)),
  });
  return { id, org, wedding };
}

export function MoodboardsPage() {
  const { t } = useTranslation();
  const { id, org, wedding } = useWedding();
  if (wedding.isPending) return <Spinner />;
  if (!wedding.data) return <FormMessage>{errorMessage(wedding.error, t)}</FormMessage>;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />
      <BoardList
        scope={teamScope(org, id)}
        canCreate={wedding.data.permissions.includes('moodboards:write')}
      />
    </div>
  );
}

export function MoodboardPage() {
  const { t } = useTranslation();
  const { boardId = '' } = useParams();
  const { id, org, wedding } = useWedding();
  if (wedding.isPending) return <Spinner />;
  if (!wedding.data) return <FormMessage>{errorMessage(wedding.error, t)}</FormMessage>;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <>
            <Link to="/app/weddings">{t('weddings.title')}</Link> /{' '}
            <Link to={`/app/weddings/${id}`}>{wedding.data.title}</Link> /{' '}
            <Link to={`/app/weddings/${id}/moodboards`}>{t('nav.moodboards')}</Link>
          </>
        }
        title={wedding.data.title}
      />
      <WeddingNav id={id} />
      <BoardView scope={teamScope(org, id)} boardId={boardId} />
    </div>
  );
}

export function PortalInspirationPage() {
  const { t } = useTranslation();
  const { project, isPending } = usePortalProject();
  if (isPending) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-4xl font-medium">{t('moodboards.portalTitle')}</h1>
      <BoardList scope={coupleScope(project.id)} canCreate />
    </div>
  );
}

export function PortalBoardPage() {
  const { t } = useTranslation();
  const { boardId = '' } = useParams();
  const { project, isPending } = usePortalProject();
  if (isPending) return <Spinner />;
  if (!project) {
    return <EmptyState title={t('portal.home.emptyTitle')} body={t('portal.home.emptyBody')} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <Link to="/portal/inspiration" className="text-sm font-medium text-accent">
        ‹ {t('moodboards.portalTitle')}
      </Link>
      <BoardView scope={coupleScope(project.id)} boardId={boardId} />
    </div>
  );
}

export function PortalMorePage() {
  const { t } = useTranslation();
  const links = [
    { to: '/portal/calendar', label: t('nav.calendar') },
    { to: '/portal/files', label: t('nav.files') },
    { to: '/portal/notifications', label: t('notifications.title') },
    { to: '/portal/privacy', label: t('privacy.title') },
    { to: '/portal/account', label: t('account.title') },
  ];
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-4xl font-medium">{t('nav.more')}</h1>
      <ul className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface">
        {links.map((link) => (
          <li key={link.to} className="border-b border-line-soft last:border-b-0">
            <Link
              to={link.to}
              className="flex min-h-14 items-center justify-between px-4 text-[15px]"
            >
              {link.label}
              <ChevronRight aria-hidden="true" className="size-4 text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
