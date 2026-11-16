import { expect, test } from '@playwright/test';

import {
  acceptInvitation,
  createOrganization,
  fullStack,
  invitationTokenFromMail,
  password,
} from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

const PDF = Buffer.from('%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n');

async function subjects(to: string): Promise<string[]> {
  const mailpit = process.env.MAILPIT_URL ?? 'http://localhost:8025';
  const search = await fetch(`${mailpit}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`);
  const { messages } = (await search.json()) as { messages: { Subject: string }[] };
  return messages.map((m) => m.Subject);
}

test('documents and appointments are shared with the couple', async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const id = `${Date.now()}-${testInfo.project.name}`;
  const coupleEmail = `couple-docs-${id}@example.com`;
  await acceptInvitation(
    page,
    createOrganization(`Docs ${id}`, `d-${id}@example.com`),
    'Lena Hoffmann',
  );

  // Wedding and couple access
  await page.getByRole('link', { name: 'New wedding' }).click();
  await page.getByLabel("Couple's name").fill('Mia & Tom');
  await page
    .getByLabel('Wedding date')
    .fill(new Date(Date.now() + 200 * 86_400_000).toISOString().slice(0, 10));
  await page.getByRole('button', { name: 'Create wedding' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeVisible();
  await page.getByLabel('Email of the couple').fill(coupleEmail);
  await page.getByRole('button', { name: 'Invite' }).click();
  await expect(page.getByText(/Invited · valid until/)).toBeVisible();
  const couple = await browser.newContext({ ...testInfo.project.use, ignoreHTTPSErrors: true });
  const portal = await couple.newPage();
  await portal.goto(`/invite/${await invitationTokenFromMail(coupleEmail)}`);
  await portal.getByLabel('Full name').fill('Mia Becker');
  await portal.getByLabel('Choose a password').fill(password);
  await portal.getByRole('button', { name: 'Open my wedding portal' }).click();
  await expect(portal.getByText('Hi Mia')).toBeVisible();

  // Upload a shared document
  const sections = page.getByRole('navigation', { name: 'Wedding sections' });
  await sections.getByRole('link', { name: 'Documents' }).click();
  await page.getByRole('button', { name: 'Upload document' }).click();
  const upload = page.getByRole('dialog', { name: 'Upload document' });
  await upload.getByLabel('File').setInputFiles({
    name: 'Menu.pdf',
    mimeType: 'application/pdf',
    buffer: PDF,
  });
  await upload.getByLabel('Category').selectOption('planning');
  await upload.getByLabel(/Share with the couple/).check();
  await upload.getByRole('button', { name: 'Upload document' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  const row = page.getByRole('listitem').filter({ hasText: 'Menu' });
  await expect(row.getByText('Shared with couple')).toBeVisible();
  // With VIRUS_SCAN=clamav the download appears once the scan passed.
  await expect(row.getByRole('link', { name: 'Download' })).toBeVisible({ timeout: 90_000 });
  const download = page.waitForEvent('download');
  await row.getByRole('link', { name: 'Download' }).click();
  expect((await download).suggestedFilename()).toBe('Menu.pdf');
  await expect.poll(() => subjects(coupleEmail)).toContain('New document: Menu');

  // A disguised file is refused
  await page.getByRole('button', { name: 'Upload document' }).click();
  await upload.getByLabel('File').setInputFiles({
    name: 'invoice.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('MZ this is not a pdf'),
  });
  await upload.getByRole('button', { name: 'Upload document' }).click();
  await expect(upload.getByText(/not accepted/)).toBeVisible();
  await upload.getByRole('button', { name: 'Cancel' }).click();

  // A shared appointment
  await sections.getByRole('link', { name: 'Calendar' }).click();
  await page.getByRole('button', { name: 'New appointment' }).click();
  const event = page.getByRole('dialog', { name: 'New appointment' });
  const day = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
  await event.getByLabel('Title', { exact: true }).fill('Cake tasting');
  await event.getByLabel('Date', { exact: true }).fill(day);
  await event.getByLabel('Start', { exact: true }).fill('15:00');
  await event.getByLabel('End', { exact: true }).fill('16:30');
  await event.getByLabel('Location').fill('Konditorei Süß');
  await event.getByLabel(/Show to the couple/).check();
  await event.getByRole('button', { name: 'Add appointment' }).click();
  await expect(page.getByRole('button', { name: /Cake tasting/ })).toBeVisible();

  // Organization calendar and subscription feed
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Calendar' })
    .click();
  await expect(page.getByRole('link', { name: /Cake tasting/ }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Subscribe' }).click();
  const feed = page.getByRole('dialog', { name: 'Subscribe to your calendar' });
  await feed.getByRole('button', { name: 'Create link' }).click();
  const url = await feed.getByLabel('Your private link').inputValue();
  const ics = await page.request.get(url);
  expect(ics.ok()).toBe(true);
  expect(await ics.text()).toContain('SUMMARY:Cake tasting · Mia & Tom');

  // The couple sees both
  const nav = portal.getByRole('navigation', { name: 'Portal' });
  await nav.getByRole('link', { name: 'More' }).click();
  await portal.getByRole('main').getByRole('link', { name: 'Files' }).click();
  await expect(portal.getByText('Menu')).toBeVisible();
  await nav.getByRole('link', { name: 'More' }).click();
  await portal.getByRole('main').getByRole('link', { name: 'Calendar' }).click();
  await expect(portal.getByText('Cake tasting')).toBeVisible();
  await expect(portal.getByText('Your wedding day')).toBeVisible();
  await couple.close();
});
