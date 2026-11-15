import { expect, test } from '@playwright/test';

import { acceptInvitation, createOrganization, fullStack } from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

test('a planner creates a wedding from the template and books a vendor', async ({
  page,
}, testInfo) => {
  const id = `${Date.now()}-${testInfo.project.name}`;
  await acceptInvitation(
    page,
    createOrganization(`Weddings ${id}`, `w-${id}@example.com`),
    'Lena Hoffmann',
  );

  // Vendor directory
  await page.getByRole('link', { name: 'Vendors' }).click();
  await page.getByRole('button', { name: 'New vendor' }).click();
  const vendorDialog = page.getByRole('dialog', { name: 'New vendor' });
  await vendorDialog.getByLabel('Name').fill('Blumenwerk');
  await vendorDialog.getByLabel('Category').selectOption('flowers');
  await vendorDialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('Blumenwerk')).toBeVisible();

  // New wedding from the default template
  await page.getByRole('link', { name: 'Weddings' }).click();
  await page.getByRole('link', { name: 'New wedding' }).click();
  await page.getByLabel("Couple's name").fill('Mia & Tom');
  const date = new Date(Date.now() + 300 * 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel('Wedding date').fill(date);
  await page.getByLabel('Venue', { exact: true }).fill('Gut Lindenhof');
  await page.getByLabel('Expected guests').fill('120');
  await page.getByRole('button', { name: 'Create wedding' }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeVisible();
  await expect(page.getByText('Venue and date secured')).toBeVisible();
  await expect(page.getByText('Day-of timeline approved')).toBeVisible();

  // Book the vendor for this wedding
  await page.getByLabel('Add a vendor').selectOption({ label: 'Blumenwerk · Flowers' });
  await page.getByRole('button', { name: 'Add', exact: true }).last().click();
  await page.getByLabel('Status of Blumenwerk').selectOption('booked');
  await expect(page.getByLabel('Status of Blumenwerk')).toHaveValue('booked');

  // Edit details with optimistic locking
  await page.getByRole('button', { name: 'Edit details' }).click();
  await page.getByRole('dialog').getByLabel('Expected guests').fill('130');
  await page.getByRole('dialog').getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('130 guests')).toBeVisible();

  // The client was created along with the wedding
  await page.getByRole('link', { name: 'Clients' }).click();
  await expect(page.getByRole('link', { name: 'Mia & Tom' })).toBeVisible();

  // Dashboard shows the wedding
  await page.getByRole('link', { name: 'Dashboard' }).click();
  await expect(page.getByRole('link', { name: /Mia & Tom/ })).toBeVisible();
});
