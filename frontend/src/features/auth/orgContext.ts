import { createContext } from 'react';

import type { Membership } from './session';

export interface OrgContextValue {
  membership: Membership;
  teamMemberships: Membership[];
  isAdmin: boolean;
  switchTo: (organizationId: string) => void;
}

export const OrgContext = createContext<OrgContextValue | null>(null);
