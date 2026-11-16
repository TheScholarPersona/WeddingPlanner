import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { ApiError } from '@/lib/api/client';

/**
 * When an organization requires two-factor authentication and the user has not set it up,
 * every request to that organization answers `two_factor_required`: send them to set it up.
 */
function onError(error: Error) {
  if (
    error instanceof ApiError &&
    error.code === 'two_factor_required' &&
    !window.location.pathname.startsWith('/app/account') &&
    !window.location.pathname.startsWith('/admin')
  ) {
    window.location.assign('/app/account?required=2fa');
  }
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
        queryCache: new QueryCache({ onError }),
        mutationCache: new MutationCache({ onError }),
      }),
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
