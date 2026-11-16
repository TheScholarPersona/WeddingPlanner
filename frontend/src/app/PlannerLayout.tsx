import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router';

import { useMe } from '@/features/auth/session';
import { useActiveOrg } from '@/features/auth/useActiveOrg';
import { cn } from '@/lib/utils';

import { UserMenu } from './UserMenu';

const mainNav = [
  { to: '/app', key: 'nav.dashboard', end: true },
  { to: '/app/weddings', key: 'nav.weddings' },
  { to: '/app/clients', key: 'nav.clients' },
  { to: '/app/tasks', key: 'nav.myTasks' },
  { to: '/app/calendar', key: 'nav.calendar' },
  { to: '/app/vendors', key: 'nav.vendors' },
  { to: '/app/templates', key: 'nav.templates' },
] as const;

const footerNav = [
  { to: '/app/team', key: 'nav.team' },
  { to: '/app/settings', key: 'nav.settings' },
  { to: '/app/notifications', key: 'nav.notifications' },
  { to: '/app/account', key: 'nav.account' },
] as const;

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    'rounded-lg px-3 py-2.5 text-sm text-ink-soft hover:bg-subtle hover:text-ink',
    isActive && 'bg-accent-soft font-semibold text-ink',
  );
}

function OrganizationSwitcher() {
  const { t } = useTranslation();
  const { membership, teamMemberships, switchTo } = useActiveOrg();
  if (teamMemberships.length < 2) {
    return (
      <span className="px-3 font-display text-[26px] leading-tight font-semibold">
        {membership.organization_name}
      </span>
    );
  }
  return (
    <label className="flex flex-col gap-1 px-3">
      <span className="text-xs text-muted">{t('nav.organization')}</span>
      <select
        className="h-10 rounded-lg border border-line bg-surface px-2 font-display text-lg font-semibold"
        value={membership.organization_id}
        onChange={(e) => switchTo(e.target.value)}
      >
        {teamMemberships.map((m) => (
          <option key={m.organization_id} value={m.organization_id}>
            {m.organization_name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function PlannerLayout() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  return (
    <div className="flex min-h-screen flex-wrap bg-ground">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-3">
        {t('app.skipToContent')}
      </a>
      <nav
        aria-label={t('nav.main')}
        className="flex max-w-full flex-[1_1_220px] flex-col gap-8 border-line bg-surface px-5 py-8 md:max-w-[260px] md:border-r"
      >
        <OrganizationSwitcher />
        <div className="flex flex-wrap gap-1 md:flex-col">
          {mainNav.map((item) => (
            <NavLink key={item.to} to={item.to} end={'end' in item} className={navClass}>
              {t(item.key)}
            </NavLink>
          ))}
        </div>
        <div className="mt-auto flex flex-col gap-3">
          <div className="flex flex-wrap gap-1 md:flex-col">
            {footerNav.map((item) => (
              <NavLink key={item.to} to={item.to} className={navClass}>
                {t(item.key)}
              </NavLink>
            ))}
            {me?.is_platform_admin && (
              <NavLink to="/admin" className={navClass}>
                {t('nav.admin')}
              </NavLink>
            )}
          </div>
          <div className="border-t border-line pt-3">
            <UserMenu />
          </div>
        </div>
      </nav>
      <main id="main" className="min-w-0 flex-[999_1_560px] px-6 py-10 md:px-12">
        <Outlet />
      </main>
    </div>
  );
}
