import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const prefs = { task_assigned: true, comments: true, documents: true, daily_digest: true };

test('team members switch email notifications', async () => {
  const path = `/orgs/${ORG_ID}/notification-preferences`;
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${path}`]: [200, prefs],
    [`PATCH ${path}`]: [200, { ...prefs, daily_digest: false }],
  });
  const user = userEvent.setup();
  renderRoute('/app/notifications');

  const digest = await screen.findByRole('switch', { name: /Daily overview/ });
  expect(digest).toBeChecked();
  await user.click(digest);

  await waitFor(() =>
    expect(screen.getByRole('switch', { name: /Daily overview/ })).not.toBeChecked(),
  );
  expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ daily_digest: false });
  expect(screen.getByRole('switch', { name: /Tasks assigned to me/ })).toBeInTheDocument();
});

test('couples see the settings that apply to them', async () => {
  mockApi({
    'GET /me': [200, meFixture('client')],
    'GET /portal/projects': [
      200,
      [
        {
          id: 'w1',
          title: 'Mia & Tom',
          wedding_date: null,
          organization: { name: 'Atelier', accent_color: null },
        },
      ],
    ],
    'GET /portal/projects/w1/notification-preferences': [200, prefs],
  });

  renderRoute('/portal/notifications');

  expect(await screen.findByRole('switch', { name: /Documents/ })).toBeChecked();
  expect(screen.queryByRole('switch', { name: /Tasks assigned to me/ })).not.toBeInTheDocument();
  expect(screen.getByText(/When your planner shares a document/)).toBeInTheDocument();
});
