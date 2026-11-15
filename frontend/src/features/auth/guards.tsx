import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import { Spinner } from '@/components/Spinner';

import { ActiveOrgProvider } from './ActiveOrgProvider';
import { homePathFor, isTeamRole, useMe, type Me } from './session';

function useGuard(): { me: Me | null | undefined; loading: boolean; next: string } {
  const { data, isPending } = useMe();
  const location = useLocation();
  return { me: data, loading: isPending, next: location.pathname + location.search };
}

/** Planner area: needs a session and a team membership (org admin or member). */
export function RequireTeam({ children }: { children: ReactNode }) {
  const { me, loading, next } = useGuard();
  if (loading) return <Spinner fullPage />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  if (!me.memberships.some(isTeamRole)) return <Navigate to={homePathFor(me)} replace />;
  return <ActiveOrgProvider me={me}>{children}</ActiveOrgProvider>;
}

/** Client portal: needs a session and a client membership. */
export function RequireClient({ children }: { children: ReactNode }) {
  const { me, loading, next } = useGuard();
  if (loading) return <Spinner fullPage />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  if (!me.memberships.some((m) => m.role === 'client')) {
    return <Navigate to={homePathFor(me)} replace />;
  }
  return <>{children}</>;
}
