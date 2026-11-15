import { expect, test } from '@playwright/test';

import { acceptInvitation, createOrganization, fullStack } from './support';

test.skip(!fullStack, 'needs the Docker stack (E2E_FULL_STACK=1)');

test('a planner works through tasks, shares one with the couple and comments', async ({
  page,
}, testInfo) => {
  const id = `${Date.now()}-${testInfo.project.name}`;
  await acceptInvitation(
    page,
    createOrganization(`Tasks ${id}`, `t-${id}@example.com`),
    'Lena Hoffmann',
  );

  await page.getByRole('link', { name: 'New wedding' }).click();
  await page.getByLabel("Couple's name").fill('Mia & Tom');
  const date = new Date(Date.now() + 400 * 86_400_000).toISOString().slice(0, 10);
  await page.getByLabel('Wedding date').fill(date);
  await page.getByRole('button', { name: 'Create wedding' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeVisible();

  // Tasks tab
  await page
    .getByRole('navigation', { name: 'Wedding sections' })
    .getByRole('link', { name: 'Tasks' })
    .click();
  await expect(page.getByText('Shortlist venues')).toBeVisible();

  // Complete a template task
  // Completed tasks leave the "Open" view and show up under "Done"
  await page.getByLabel('Mark “Shortlist venues” as done').click();
  await expect(page.getByText('Shortlist venues')).toBeHidden();
  await page.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByLabel('Mark “Shortlist venues” as done')).toBeChecked();

  // Add a task, open it, share it and comment
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await page.getByLabel('New task').fill('Book a jazz trio');
  await page.getByRole('button', { name: 'Add task' }).click();
  await page.getByRole('button', { name: /Book a jazz trio/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Book a jazz trio' });
  await dialog.getByLabel('Visibility').selectOption('client');
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog.getByText('Changes saved.')).toBeVisible();
  await dialog.getByLabel('Write a comment').fill('Asked two trios for quotes.');
  await dialog.getByRole('button', { name: 'Post comment' }).click();
  await expect(dialog.getByText('Asked two trios for quotes.')).toBeVisible();
  await page.keyboard.press('Escape');

  // Activity on the overview
  await page
    .getByRole('navigation', { name: 'Wedding sections' })
    .getByRole('link', { name: 'Overview' })
    .click();
  await expect(page.getByText(/commented on “Book a jazz trio”/)).toBeVisible();
  await expect(page.getByText(/completed “Shortlist venues”/)).toBeVisible();

  // Assigned to me → My tasks
  await page
    .getByRole('navigation', { name: 'Wedding sections' })
    .getByRole('link', { name: 'Tasks' })
    .click();
  await page.getByRole('button', { name: /Book a jazz trio/ }).click();
  await page.getByRole('dialog').getByLabel('Assigned to').selectOption({ label: 'Lena Hoffmann' });
  await page.getByRole('dialog').getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('dialog').getByText('Changes saved.')).toBeVisible();
  await page.keyboard.press('Escape');
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'My tasks' })
    .click();
  await expect(page.getByText('Book a jazz trio')).toBeVisible();
});
