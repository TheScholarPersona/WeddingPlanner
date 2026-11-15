import { expect, test } from '@playwright/test';

import {
  acceptInvitation,
  createOrganization,
  fullStack,
  invitationTokenFromMail,
  password,
} from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

test('the planner shares budget and tasks, the couple works in the portal', async ({
  browser,
  page,
}, testInfo) => {
  const id = `${Date.now()}-${testInfo.project.name}`;
  const coupleEmail = `couple-${id}@example.com`;
  await acceptInvitation(
    page,
    createOrganization(`Portal ${id}`, `p-${id}@example.com`),
    'Lena Hoffmann',
  );

  // Wedding with budget
  await page.getByRole('link', { name: 'New wedding' }).click();
  await page.getByLabel("Couple's name").fill('Mia & Tom');
  await page
    .getByLabel('Wedding date')
    .fill(new Date(Date.now() + 300 * 86_400_000).toISOString().slice(0, 10));
  await page.getByRole('button', { name: 'Create wedding' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeVisible();
  const sections = page.getByRole('navigation', { name: 'Wedding sections' });

  await sections.getByRole('link', { name: 'Budget' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Total budget').fill('38000');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await page.getByLabel('New item in Venue').fill('Gut Lindenhof');
  await page.getByLabel('Planned amount for Venue').fill('12500');
  await page
    .getByRole('heading', { name: 'Venue' })
    .locator('..')
    .locator('..')
    .getByRole('button', { name: 'Add' })
    .click();
  await page.getByRole('button', { name: 'Gut Lindenhof' }).click();
  const item = page.getByRole('dialog', { name: 'Gut Lindenhof' });
  await item.getByLabel('Contracted').fill('12500');
  await item.getByLabel('Internal cost').fill('9000');
  await item.getByLabel('Visibility').selectOption('client');
  await item.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();

  // Invite the couple
  await sections.getByRole('link', { name: 'Overview' }).click();
  await page.getByLabel('Email of the couple').fill(coupleEmail);
  await page.getByRole('button', { name: 'Invite' }).click();
  await expect(page.getByText(/Invited · valid until/)).toBeVisible();

  // The couple accepts and uses the portal (separate browser session)
  const couple = await browser.newContext({ ...testInfo.project.use, ignoreHTTPSErrors: true });
  const portal = await couple.newPage();
  await portal.goto(`/invite/${await invitationTokenFromMail(coupleEmail)}`);
  await expect(portal.getByText(/invited you to your wedding portal/)).toBeVisible();
  await portal.getByLabel('Full name').fill('Mia Becker');
  await portal.getByLabel('Choose a password').fill(password);
  await portal.getByRole('button', { name: 'Open my wedding portal' }).click();

  await expect(portal.getByText('Hi Mia')).toBeVisible();
  await expect(portal.getByText('Your next steps')).toBeVisible();
  await portal.getByLabel('Mark “Agree on the overall budget” as done').click();
  await expect(portal.getByLabel('Mark “Agree on the overall budget” as done')).toBeHidden();

  await portal
    .getByRole('navigation', { name: 'Portal' })
    .getByRole('link', { name: 'Budget' })
    .click();
  await expect(portal.getByText('Gut Lindenhof')).toBeVisible();
  await expect(portal.getByText(/12\.500,00/).first()).toBeVisible();
  await expect(portal.getByText(/9\.000/)).toHaveCount(0);
  await couple.close();

  // The planner sees what the couple did
  await page.reload();
  await expect(
    page.getByText(/Mia Becker\s+completed “Agree on the overall budget”/),
  ).toBeVisible();
});
