import type { TFunction } from 'i18next';

import { ApiError } from './client';

/** A user-facing English message for any error; codes map to locale entries. */
export function errorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const key = `errors.codes.${error.code}`;
    const translated = t(key as never, { defaultValue: '' }) as string;
    return translated || error.problem.detail || error.problem.title;
  }
  return t('errors.generic');
}

export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.problem.errors) return {};
  return Object.fromEntries(error.problem.errors.map((e) => [e.field, e.message]));
}
