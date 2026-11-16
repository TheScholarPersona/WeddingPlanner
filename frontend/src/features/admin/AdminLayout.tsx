import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, NavLink, Outlet } from 'react-router';

import { Spinner } from '@/components/Spinner';
import { UserMenu } from '@/app/UserMenu';
import { isTeamRole, useMe } from '@/features/auth/session';
import { cn } from '@/lib/utils';

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMe();
  if (isPending) return <Spinner fullPage />;
  if (!me) return <Navigate to="/login?next=%2Fadmin" replace />;
  if (!me.is_platform_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function AdminLayout() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const link = ({ isActive }: { isActive: boolean }) =>
    cn('text-sm', isActive ? 'font-semibold text-ink' : 'text-ink-soft hover:text-ink');
  return (
    <div className="min-h-screen bg-ground">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line bg-surface px-6 py-4">
        <div className="flex flex-wrap items-center gap-6">
          <span className="font-display text-2xl font-semibold">{t('admin.title')}</span>
          <nav aria-label={t('admin.title')} className="flex gap-5">
            <NavLink to="/admin" end className={link}>
              {t('admin.organizations')}
            </NavLink>
            <NavLink to="/admin/account" className={link}>
              {t('account.title')}
            </NavLink>
            {me?.memberships.some(isTeamRole) && (
              <Link to="/app" className="text-sm text-ink-soft hover:text-ink">
                {t('admin.backToApp')}
              </Link>
            )}
          </nav>
        </div>
        <UserMenu />
      </header>
      <main id="main" className="mx-auto max-w-6xl px-6 py-10">
        <Outlet />
      </main>
    </div>
  );
}
