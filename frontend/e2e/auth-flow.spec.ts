import { execSync } from 'node:child_process';
import path from 'node:path';

import { expect, test } from '@playwright/test';

/**
 * Full stack: needs `make up` and runs against https://localhost.
 *   E2E_FULL_STACK=1 E2E_BASE_URL=https://localhost npx playwright test auth-flow
 */
test.skip(!process.env.E2E_FULL_STACK, 'needs the Docker stack (E2E_FULL_STACK=1)');

const repoRoot = path.resolve(import.meta.dirname, '..', '..');
const password = 'correct horse battery staple';

function createOrganization(name: string, adminEmail: string): string {
  const output = execSync(
    `docker compose exec -T api python -m app.cli create-organization --name "${name}" --admin-email ${adminEmail}`,
    { cwd: repoRoot, encoding: 'utf-8' },
  );
  const match = output.match(/\/invite\/([A-Za-z0-9_-]+)/);
  if (!match?.[1]) throw new Error(`No invitation link in: ${output}`);
  return match[1];
}

test('an invited admin sets up the account, manages the team and signs in again', async ({
  page,
}, testInfo) => {
  const id = `${Date.now()}-${testInfo.project.name}`;
  const adminEmail = `admin-${id}@example.com`;
  const token = createOrganization(`E2E Atelier ${id}`, adminEmail);

  await page.goto(`/invite/${token}`);
  await expect(page.getByRole('heading', { name: "You're invited" })).toBeVisible();
  await page.getByLabel('Full name').fill('Erika Example');
  await page.getByLabel('Choose a password').fill(password);
  await page.getByRole('button', { name: /^Join E2E Atelier/ }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'Good morning, Erika' })).toBeVisible();

  await page.getByRole('link', { name: 'Team' }).click();
  await page.getByLabel('Email').fill(`planner-${id}@example.com`);
  await page.getByRole('button', { name: 'Send invitation' }).click();
  await expect(page.getByText(`planner-${id}@example.com`)).toBeVisible();

  await page.getByRole('link', { name: 'Settings' }).click();
  await page.getByLabel('Organization name').fill(`E2E Atelier ${id} (renamed)`);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('Changes saved.')).toBeVisible();
  await expect(page.getByText('updated the organization settings')).toBeVisible();
  await expect(page.getByText('sent an invitation').first()).toBeVisible();

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel('Email').fill(adminEmail);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Good morning, Erika' })).toBeVisible();
});
