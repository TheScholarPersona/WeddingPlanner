import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const O = `/orgs/${ORG_ID}`;
const client = {
  id: 'c1',
  display_name: 'Mia & Tom',
  status: 'booked',
  source: null,
  primary_contact: 'Mia Becker',
  primary_email: 'mia@example.com',
  next_wedding_date: '2027-06-12',
  project_count: 1,
  created_at: '2026-10-01T10:00:00Z',
};

test('lists clients and creates a new enquiry with its primary contact', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${O}/clients`]: [200, [client]],
    [`POST ${O}/clients`]: [201, { ...client, id: 'c2', display_name: 'Anna & Lukas' }],
    [`GET ${O}/clients/c2`]: [
      200,
      {
        ...client,
        id: 'c2',
        display_name: 'Anna & Lukas',
        status: 'inquiry',
        notes_internal: null,
        contacts: [],
        projects: [],
      },
    ],
  });
  const user = userEvent.setup();
  const { router } = renderRoute('/app/clients');

  const row = (await screen.findByText('Mia & Tom')).closest('tr')!;
  expect(within(row).getByText('Booked')).toBeInTheDocument();
  expect(within(row).getByText('Mia Becker', { exact: false })).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'New client' }));
  await user.type(screen.getByLabelText('Name'), 'Anna & Lukas');
  await user.type(screen.getByLabelText('First name'), 'Anna');
  await user.click(screen.getByRole('button', { name: 'Create client' }));

  await waitFor(() => expect(router.state.location.pathname).toBe('/app/clients/c2'));
  expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
    display_name: 'Anna & Lukas',
    contacts: [{ first_name: 'Anna' }],
  });
});
