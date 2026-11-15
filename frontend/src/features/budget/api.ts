import type { Schemas } from '@/lib/api/client';

export type BudgetView = Schemas['BudgetOut'];
export type BudgetItem = Schemas['ItemOut'];
export type BudgetCategory = Schemas['CategoryOut'];

export const budgetKey = (org: string, project: string) =>
  ['org', org, 'wedding', project, 'budget'] as const;

export const budgetPath = (org: string, project: string) =>
  `/orgs/${org}/projects/${project}/budget`;

/** "1250.50" (form input, euros) → 125050 cents; empty → null. */
export function toCents(value: string): number | null {
  const normalized = value.trim().replace(/\s/g, '').replace(',', '.');
  if (!normalized) return null;
  const amount = Number(normalized);
  return Number.isFinite(amount) ? Math.round(amount * 100) : null;
}

/** 125050 cents → "1250.50" for a number input; null → "". */
export function toInput(cents: number | null | undefined): string {
  return cents == null ? '' : (cents / 100).toFixed(2);
}
