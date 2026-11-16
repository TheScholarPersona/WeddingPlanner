import { CalendarDays, CircleDollarSign, FileText, House, ListChecks } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router';

import { useMe } from '@/features/auth/session';
import { cn } from '@/lib/utils';

import { UserMenu } from './UserMenu';

const items = [
  { to: '/portal', key: 'nav.home', icon: House, end: true },
  { to: '/portal/tasks', key: 'nav.tasks', icon: ListChecks },
  { to: '/portal/budget', key: 'nav.budget', icon: CircleDollarSign },
  { to: '/portal/calendar', key: 'nav.calendar', icon: CalendarDays },
  { to: '/portal/files', key: 'nav.files', icon: FileText },
] as const;

export function PortalLayout() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const organization = me?.memberships.find((m) => m.role === 'client')?.organization_name;
  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col bg-ground">
      <header className="flex items-center justify-between gap-4 px-5 pt-6">
        <span className="font-display text-xl font-semibold">{organization}</span>
        <UserMenu compact settingsPath="/portal/account" />
      </header>
      <main id="main" className="flex-1 px-5 pt-6 pb-28">
        <Outlet />
      </main>
      <nav
        aria-label={t('nav.portal')}
        className="fixed inset-x-0 bottom-0 grid grid-cols-5 border-t border-line bg-surface px-1 pt-2 pb-5"
      >
        {items.map(({ to, key, icon: Icon, ...rest }) => (
          <NavLink
            key={to}
            to={to}
            end={'end' in rest}
            className={({ isActive }) =>
              cn(
                'flex min-h-11 flex-col items-center justify-center gap-1 text-[11px] text-muted',
                isActive && 'font-semibold text-accent-strong',
              )
            }
          >
            <Icon aria-hidden="true" className="size-[22px]" strokeWidth={1.8} />
            {t(key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
