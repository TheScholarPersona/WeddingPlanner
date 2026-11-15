import { expect, test } from '@playwright/test';

test('login page renders and links into both app areas', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();

  await page.getByRole('link', { name: 'Open planner app' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Good morning' })).toBeVisible();

  await page.goto('/portal');
  await expect(page.getByRole('navigation', { name: 'Portal' })).toBeVisible();
});

test('page has no horizontal scroll at its viewport width', async ({ page }) => {
  await page.goto('/login');

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
