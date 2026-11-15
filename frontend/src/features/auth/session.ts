import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError, type Schemas } from '@/lib/api/client';

export type Me = Schemas['MeOut'];
export type Membership = Schemas['MembershipOut'];

export const meQueryKey = ['me'] as const;

/** The signed-in user, or null when there is no valid session. */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async () => {
      try {
        return await api<Me>('GET', '/me');
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api('POST', '/auth/logout'),
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData(meQueryKey, null);
    },
  });
}

export const isTeamRole = (m: Membership) => m.role === 'org_admin' || m.role === 'member';

/** Where a user lands after signing in. */
export function homePathFor(me: Me): string {
  if (me.memberships.some(isTeamRole)) return '/app';
  if (me.memberships.length > 0) return '/portal';
  return '/no-access';
}

/** Only follow same-site relative paths after login. */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : null;
}
