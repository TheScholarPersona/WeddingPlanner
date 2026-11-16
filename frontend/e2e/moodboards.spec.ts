import { expect, test } from '@playwright/test';

import { fullStack, seedDemo, signIn } from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

// A tiny valid PNG (2x2 pixels), generated: no third-party image.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP4z8DwHwyBNAMDA8N/AABQ1gL+qZLjLQAAAABJRU5ErkJggg==',
  'base64',
);

test('planner and couple build a moodboard, the planner exports a PDF', async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const demo = seedDemo(`Moodboards ${Date.now()}-${testInfo.project.name}`);

  // Planner: open the shared board, add an image, select one, export
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
  await page
    .getByRole('navigation', { name: 'Wedding sections' })
    .getByRole('link', { name: 'Moodboards' })
    .click();
  await expect(page.getByText('From the couple')).toBeVisible(); // "Our ideas"
  await page.getByRole('link', { name: /Overall look/ }).click();
  await expect(page.getByRole('heading', { name: 'Flowers' })).toBeVisible();

  await page.getByLabel('Add images to Cake').setInputFiles({
    name: 'cake-idea.png',
    mimeType: 'image/png',
    buffer: PNG,
  });
  const cake = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Cake' }) });
  await expect(cake.getByRole('img')).toHaveCount(2, { timeout: 60_000 });

  await page.getByRole('button', { name: /^Garden roses and ranunculus/ }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Selected' }).click();
  await expect(dialog.getByRole('button', { name: 'Selected' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await dialog.getByRole('button', { name: 'Close' }).click();

  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'PDF: selected' }).click();
  expect((await download).suggestedFilename()).toBe('moodboard-Overall-look.pdf');

  // Couple: hearts and comments on the phone (separate session)
  const couple = await browser.newContext({ ...testInfo.project.use, ignoreHTTPSErrors: true });
  const portal = await couple.newPage();
  await signIn(portal, demo.couple.email, demo.couple.password);
  await expect(portal.getByText(/^Hi /)).toBeVisible();
  await portal
    .getByRole('navigation', { name: 'Portal' })
    .getByRole('link', { name: 'Inspiration' })
    .click();
  await portal.getByRole('link', { name: /Overall look/ }).click();
  await portal.getByRole('button', { name: /^Garden roses and ranunculus/ }).click();
  const view = portal.getByRole('dialog');
  await expect(view.getByText('Your planner selected this one.')).toBeVisible();
  await expect(view.getByRole('button', { name: 'Selected' })).toHaveCount(0);
  await view.getByRole('button', { name: 'Heart' }).click();
  await expect(view.getByRole('button', { name: 'Hearted' })).toBeVisible();
  await view.getByLabel('Write a comment').fill('Yes, these!');
  await view.getByRole('button', { name: 'Send' }).click();
  await expect(view.getByText('Yes, these!')).toBeVisible();
  await couple.close();
});
