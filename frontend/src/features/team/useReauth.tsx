import { useState } from 'react';

import { ApiError } from '@/lib/api/client';

import { ReauthDialog } from './ReauthDialog';

/**
 * Runs a sensitive action; if the server answers `reauth_required`, asks for the password
 * and retries once.
 */
export function useReauth() {
  const [pending, setPending] = useState<(() => Promise<unknown>) | null>(null);

  /** `onResult` also receives the result of the retry after the password was confirmed. */
  async function run<T>(
    action: () => Promise<T>,
    onResult?: (result: T) => void,
  ): Promise<T | undefined> {
    try {
      const result = await action();
      onResult?.(result);
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.code === 'reauth_required') {
        setPending(() => async () => {
          const result = await action();
          onResult?.(result);
        });
        return undefined;
      }
      throw error;
    }
  }

  const dialog = pending ? (
    <ReauthDialog
      onCancel={() => setPending(null)}
      onConfirmed={async () => {
        const action = pending;
        setPending(null);
        await action();
      }}
    />
  ) : null;

  return { run, dialog };
}
