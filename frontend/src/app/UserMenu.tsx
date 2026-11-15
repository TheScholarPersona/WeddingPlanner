import { useTranslation } from 'react-i18next';
import { Bell } from 'lucide-react';
import { Link, useNavigate } from 'react-router';

import { Button } from '@/components/ui/button';
import { useLogout, useMe } from '@/features/auth/session';

export function UserMenu({
  compact = false,
  settingsPath,
}: {
  compact?: boolean;
  settingsPath: string;
}) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!me) return null;

  const initials = me.full_name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent-strong"
      >
        {initials}
      </span>
      {!compact && (
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{me.full_name}</span>
      )}
      <Button asChild variant="ghost" size="icon" className="size-9">
        <Link
          to={settingsPath}
          aria-label={t('notifications.title')}
          title={t('notifications.title')}
        >
          <Bell aria-hidden="true" className="size-4" />
        </Link>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => logout.mutate(undefined, { onSettled: () => void navigate('/login') })}
      >
        {t('nav.signOut')}
      </Button>
    </div>
  );
}
