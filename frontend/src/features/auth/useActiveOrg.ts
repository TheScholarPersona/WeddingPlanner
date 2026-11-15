import { useContext } from 'react';

import { OrgContext, type OrgContextValue } from './orgContext';

export function useActiveOrg(): OrgContextValue {
  const value = useContext(OrgContext);
  if (!value) throw new Error('useActiveOrg must be used inside ActiveOrgProvider');
  return value;
}
