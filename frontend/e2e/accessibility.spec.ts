import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

import { fullStack, seedDemo, signIn, type DemoLogins } from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

let demo: DemoLogins;
// eslint-disable-next-line no-empty-pattern -- Playwright passes fixtures first
test.beforeAll(({}, testInfo) => {
  demo = seedDemo(`A11y ${Date.now()}-${testInfo.project.name}`);
});

async function audit(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('main')).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const summary = results.violations.map(
    (v) => `${path}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  );
  expect(summary).toEqual([]);
}

test('planner pages meet WCAG 2.2 AA', async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, demo.admin.email, demo.admin.password);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Good');
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Weddings' })
    .click();
  await page
    .getByRole('link', { name: /Lena & Jonas/ })
    .first()
    .click();
  const wedding = new URL(page.url()).pathname;

  for (const path of [
    '/app',
    '/app/weddings',
    wedding,
    `${wedding}/tasks`,
    `${wedding}/budget`,
    `${wedding}/documents`,
    `${wedding}/calendar`,
    '/app/tasks',
    '/app/calendar',
    '/app/clients',
    '/app/vendors',
    '/app/team',
    '/app/settings',
    '/app/notifications',
    '/app/account',
  ]) {
    await audit(page, path);
  }
});

test('portal pages meet WCAG 2.2 AA', async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, demo.couple.email, demo.couple.password);
  await expect(page.getByText(/^Hi /)).toBeVisible();
  for (const path of [
    '/portal',
    '/portal/tasks',
    '/portal/budget',
    '/portal/calendar',
    '/portal/files',
    '/portal/privacy',
    '/portal/notifications',
    '/portal/account',
  ]) {
    await audit(page, path);
  }
});

test('sign-in page meets WCAG 2.2 AA', async ({ page }) => {
  await audit(page, '/login');
});
