import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { mockApi, ORG_ID } from '@/test/mockApi';

import { SupportAccessCard } from './SecuritySettings';

afterEach(() => vi.restoreAllMocks());

const path = `/orgs/${ORG_ID}/support-access`;

function renderCard() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SupportAccessCard orgId={ORG_ID} />
    </QueryClientProvider>,
  );
}

test('org admins grant support access for a few days with a reason', async () => {
  let granted = false;
  const grant = {
    id: 'g1',
    reason: 'Login problem',
    expires_at: '2026-11-30T10:00:00Z',
    revoked_at: null,
    active: true,
  };
  const { calls } = mockApi({
    [`GET ${path}`]: () => [200, granted ? [grant] : []],
    [`POST ${path}`]: () => {
      granted = true;
      return [201, grant];
    },
  });
  const user = userEvent.setup();
  renderCard();

  await user.selectOptions(await screen.findByLabelText('Duration'), '7');
  await user.type(screen.getByLabelText('Reason (optional)'), 'Login problem');
  await user.click(screen.getByRole('button', { name: 'Grant access' }));

  expect(
    await screen.findByText('Support access is active until 30.11.2026 · Login problem'),
  ).toBeInTheDocument();
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
    days: 7,
    reason: 'Login problem',
  });
  await waitFor(() => expect(screen.getByRole('button', { name: 'End now' })).toBeEnabled());
});
