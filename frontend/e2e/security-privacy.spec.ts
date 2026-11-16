import { execSync } from 'node:child_process';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { acceptInvitation, createOrganization, fullStack, password, signIn, totp } from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

const repoRoot = path.resolve(import.meta.dirname, '..', '..');

test('two-factor sign-in, support access and client data export', async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const id = `${Date.now()}-${testInfo.project.name}`;
  const email = `sec-${id}@example.com`;
  await acceptInvitation(page, createOrganization(`Secure ${id}`, email), 'Lena Hoffmann');

  // Turn on 2FA in the account
  await page.goto('/app/account');
  await page.getByRole('button', { name: 'Turn on' }).click();
  const secret = (await page.locator('code').innerText()).trim();
  await page.getByLabel('Code from the app').fill(totp(secret));
  await page.getByRole('button', { name: 'Turn on' }).click();
  const codes = page.getByRole('list', { name: 'Recovery codes' });
  await expect(codes.getByRole('listitem')).toHaveCount(10);
  await page.getByRole('button', { name: 'I saved them' }).click();
  await expect(page.getByText('On', { exact: true })).toBeVisible();

  // Sign in again: password, then a code (the next one; the current one is used up)
  const fresh = await browser.newContext({ ...testInfo.project.use, ignoreHTTPSErrors: true });
  const second = await fresh.newPage();
  await signIn(second, email, password);
  await second.getByLabel('Authentication code').fill(totp(secret, 1));
  await second.getByRole('button', { name: 'Verify' }).click();
  await expect(second.getByRole('heading', { level: 1 })).toContainText('Good');
  await fresh.close();

  // Require 2FA for the team and grant support access
  await page.goto('/app/settings');
  await page.getByRole('switch', { name: /Require two-factor authentication/ }).click();
  await expect(page.getByRole('switch', { name: /Require two-factor/ })).toBeChecked();
  await page.getByLabel('Reason (optional)').fill('Test of support access');
  await page.getByRole('button', { name: 'Grant access' }).click();
  await expect(page.getByText(/Support access is active until/)).toBeVisible();
  await expect(page.getByText(/allowed platform support to look in/)).toBeVisible();

  // Client export
  const nav = page.getByRole('navigation', { name: 'Main' });
  await nav.getByRole('link', { name: 'Weddings' }).click();
  await page.getByRole('link', { name: 'New wedding' }).click();
  await page.getByLabel("Couple's name").fill('Mia & Tom');
  await page.getByRole('button', { name: 'Create wedding' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeVisible();
  await nav.getByRole('link', { name: 'Clients' }).click();
  await page.getByRole('link', { name: 'Mia & Tom' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Export client data' }).click();
  expect((await download).suggestedFilename()).toMatch(/^client-export-Mia.*\.zip$/);

  // Erase the client for good
  await page.getByRole('button', { name: 'Erase client' }).click();
  const erase = page.getByRole('dialog', { name: 'Erase Mia & Tom' });
  await erase.getByLabel(/Type “Mia & Tom” to confirm/).fill('Mia & Tom');
  await erase.getByRole('button', { name: 'Erase for good' }).click();
  await expect(page).toHaveURL(/\/app\/clients$/);
  await expect(page.getByRole('link', { name: 'Mia & Tom' })).toHaveCount(0);

  // The organization shows up in the platform admin overview with support access
  execSync(`docker compose exec -T api python -m app.cli grant-platform-admin --email ${email}`, {
    cwd: repoRoot,
  });
  await page.goto('/admin');
  const row = page.getByRole('row').filter({ hasText: `Secure ${id}` });
  await expect(row.getByText(/Support until/)).toBeVisible();
  await row.getByRole('link', { name: 'Open' }).click();
  await expect(page.getByText(/Read-only support access until/)).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});
