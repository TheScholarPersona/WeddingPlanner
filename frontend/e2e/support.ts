import { execSync } from 'node:child_process';
import path from 'node:path';

import { expect, type Page } from '@playwright/test';

export const fullStack = !!process.env.E2E_FULL_STACK;
export const password = 'correct horse battery staple';
const repoRoot = path.resolve(import.meta.dirname, '..', '..');

/** Creates an organization through the operator CLI and returns the admin invitation token. */
export function createOrganization(name: string, adminEmail: string): string {
  const output = execSync(
    `docker compose exec -T api python -m app.cli create-organization --name "${name}" --admin-email ${adminEmail}`,
    { cwd: repoRoot, encoding: 'utf-8' },
  );
  const match = output.match(/\/invite\/([A-Za-z0-9_-]+)/);
  if (!match?.[1]) throw new Error(`No invitation link in: ${output}`);
  return match[1];
}

export async function acceptInvitation(page: Page, token: string, name: string) {
  await page.goto(`/invite/${token}`);
  await page.getByLabel('Full name').fill(name);
  await page.getByLabel('Choose a password').fill(password);
  await page.getByRole('button', { name: /^Join / }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Good morning');
}
