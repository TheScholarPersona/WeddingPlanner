import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const O = `/orgs/${ORG_ID}`;
const vendor = (over: Record<string, unknown>) => ({
  id: 'v1',
  name: 'Blumenwerk',
  category: 'flowers',
  contact_name: 'Jana Blum',
  email: null,
  phone: null,
  website: null,
  notes_internal: null,
  rating: 5,
  project_count: 2,
  ...over,
});

test('filters the vendor directory and rates a vendor', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${O}/vendors`]: [
      200,
      [
        vendor({}),
        vendor({ id: 'v2', name: 'DJ Nord', category: 'music', rating: null, project_count: 0 }),
      ],
    ],
    [`PATCH ${O}/vendors/v2`]: [200, vendor({ id: 'v2', name: 'DJ Nord', rating: 4 })],
  });
  const user = userEvent.setup();
  renderRoute('/app/vendors');

  expect(await screen.findByText('Used in 2 weddings · ★★★★★')).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Filter by category'), 'music');
  expect(screen.queryByText('Blumenwerk')).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.selectOptions(screen.getByLabelText('Rating'), '4');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  await waitFor(() =>
    expect(calls.find((c) => c.method === 'PATCH')?.body).toMatchObject({
      name: 'DJ Nord',
      category: 'music',
      rating: 4,
    }),
  );
});
