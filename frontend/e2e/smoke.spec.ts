import { expect, test } from '@playwright/test';

test('login page renders and protected areas redirect to it', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();

  await page.goto('/app/team');
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fteam$/);
});

test('login page has no horizontal scroll at its viewport width', async ({ page }) => {
  await page.goto('/login');

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
