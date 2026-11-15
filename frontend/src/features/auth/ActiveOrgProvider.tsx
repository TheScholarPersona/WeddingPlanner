import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type ReactNode } from 'react';

import { OrgContext, type OrgContextValue } from './orgContext';
import { isTeamRole, type Me } from './session';

// Active organization in the planner area.
const STORAGE_KEY = 'activeOrganizationId';

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function ActiveOrgProvider({ me, children }: { me: Me; children: ReactNode }) {
  const teamMemberships = useMemo(() => me.memberships.filter(isTeamRole), [me.memberships]);
  const [selected, setSelected] = useState<string | null>(readStored);
  const queryClient = useQueryClient();

  const membership =
    teamMemberships.find((m) => m.organization_id === selected) ?? teamMemberships[0];

  const value = useMemo<OrgContextValue | null>(() => {
    if (!membership) return null;
    return {
      membership,
      teamMemberships,
      isAdmin: membership.role === 'org_admin',
      switchTo: (organizationId) => {
        try {
          window.localStorage.setItem(STORAGE_KEY, organizationId);
        } catch {
          // Storage may be unavailable (private mode); the choice then lasts for this page only.
        }
        setSelected(organizationId);
        void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'org' });
      },
    };
  }, [membership, teamMemberships, queryClient]);

  if (!value) return null;
  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}
