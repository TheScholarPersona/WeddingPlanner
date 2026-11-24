import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const O = `/orgs/${ORG_ID}`;
const org = {
  id: ORG_ID,
  name: 'Atelier Test',
  slug: 'atelier-test',
  accent_color: null,
  locale: 'de-DE',
  timezone: 'Europe/Berlin',
  client_access_days_after_archive: 90,
  require_2fa: false,
};

test('org admins rename the organization and read the audit log', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('org_admin')],
    [`GET ${O}`]: [200, org],
    [`PATCH ${O}`]: (body) => [200, { ...org, ...(body as object) }],
    [`GET ${O}/support-access`]: [200, []],
    [`GET ${O}/audit-log?limit=25`]: [
      200,
      {
        items: [
          {
            id: 'a1',
            created_at: '2026-11-20T09:15:00Z',
            action: 'invitation.created',
            actor_type: 'user',
            actor_name: 'Ada Admin',
            resource_type: 'invitation',
            resource_id: 'i1',
            changes: null,
            ip: null,
          },
        ],
        next_cursor: null,
      },
    ],
  });
  const user = userEvent.setup();
  renderRoute('/app/settings');

  const name = await screen.findByLabelText('Organization name');
  await user.clear(name);
  await user.type(name, 'Atelier Lumière');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(await screen.findByText('Changes saved.')).toBeInTheDocument();
  expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({
    name: 'Atelier Lumière',
    client_access_days_after_archive: 90,
  });
  const log = screen.getByText('Audit log').closest('div')!.parentElement!;
  await waitFor(() => expect(within(log).getByText('Ada Admin')).toBeInTheDocument());
  expect(within(log).getByText('sent an invitation')).toBeInTheDocument();
  expect(screen.getByRole('switch', { name: /Require two-factor/ })).not.toBeChecked();
});

test('team members see the settings read only', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${O}`]: [200, org],
  });
  renderRoute('/app/settings');

  expect(
    await screen.findByText('Only organization admins can change these settings.'),
  ).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument();
  expect(screen.queryByText('Audit log')).not.toBeInTheDocument();
});
