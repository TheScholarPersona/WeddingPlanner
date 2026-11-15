import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID, problem } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const members = [
  {
    id: 'm1',
    user_id: 'u1',
    full_name: 'Ada Admin',
    email: 'ada@example.com',
    role: 'org_admin',
    status: 'active',
    is_you: true,
    created_at: '2026-11-01T10:00:00Z',
  },
  {
    id: 'm2',
    user_id: 'u2',
    full_name: 'Max Member',
    email: 'max@example.com',
    role: 'member',
    status: 'active',
    is_you: false,
    created_at: '2026-11-02T10:00:00Z',
  },
];
const invitations = [
  {
    id: 'i1',
    email: 'pending@example.com',
    role: 'member',
    status: 'pending',
    invited_by_name: 'Ada Admin',
    created_at: '2026-11-10T10:00:00Z',
    expires_at: '2026-11-17T10:00:00Z',
  },
];

function team(extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /me': [200, meFixture()],
    [`GET /orgs/${ORG_ID}/members`]: [200, members],
    [`GET /orgs/${ORG_ID}/invitations`]: [200, invitations],
    ...extra,
  });
}

it('lists members and pending invitations', async () => {
  team();
  renderRoute('/app/team');

  expect(await screen.findByText('Max Member')).toBeInTheDocument();
  expect(screen.getByText('(you)')).toBeInTheDocument();
  expect(await screen.findByText('pending@example.com')).toBeInTheDocument();
  expect(screen.getByText('Valid until 17.11.2026', { exact: false })).toBeInTheDocument();
});

it('invites a team member', async () => {
  const { calls } = team({ [`POST /orgs/${ORG_ID}/invitations`]: [201, invitations[0]] });
  renderRoute('/app/team');

  await userEvent.type(await screen.findByLabelText('Email'), 'new@example.com');
  await userEvent.selectOptions(screen.getByLabelText('Role'), 'org_admin');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));

  expect(await screen.findByText('Invitation sent', { exact: false })).toBeInTheDocument();
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
    email: 'new@example.com',
    role: 'org_admin',
  });
});

it('asks for the password again before a sensitive change, then retries it', async () => {
  let confirmed = false;
  const { calls } = team({
    [`PATCH /orgs/${ORG_ID}/members/m2`]: () =>
      confirmed
        ? [200, { ...members[1], status: 'disabled' }]
        : [403, problem(403, 'reauth_required')],
    'POST /auth/reauth': () => {
      confirmed = true;
      return [204];
    },
  });
  renderRoute('/app/team');

  const row = (await screen.findByText('Max Member')).closest('tr')!;
  await userEvent.click(within(row).getByRole('button', { name: 'Deactivate' }));
  const dialog = await screen.findByRole('dialog', { name: 'Confirm your password' });
  await userEvent.type(within(dialog).getByLabelText('Password'), 'correct horse battery');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

  await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('hides admin tools from planners', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET /orgs/${ORG_ID}/members`]: [200, members],
  });
  renderRoute('/app/team');

  expect(await screen.findByText('Max Member')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Send invitation' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
});
