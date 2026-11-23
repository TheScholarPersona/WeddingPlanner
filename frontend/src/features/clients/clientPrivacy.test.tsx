import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { mockApi, ORG_ID } from '@/test/mockApi';

import { ClientPrivacyCard } from './ClientPrivacyCard';

afterEach(() => vi.restoreAllMocks());

function renderCard() {
  const router = createMemoryRouter(
    [
      {
        path: '/app/clients/c1',
        element: <ClientPrivacyCard org={ORG_ID} clientId="c1" name="Mia & Tom" />,
      },
      { path: '/app/clients', element: <p>Client list</p> },
    ],
    { initialEntries: ['/app/clients/c1'] },
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

test('erasing a client needs the exact name and then leaves the deleted client', async () => {
  const { calls } = mockApi({
    [`POST /orgs/${ORG_ID}/clients/c1/erase`]: [200, { weddings: 1, files: 2, portal_accounts: 1 }],
  });
  const user = userEvent.setup();
  const router = renderCard();

  expect(screen.getByRole('link', { name: 'Export client data' })).toHaveAttribute(
    'href',
    `/api/v1/orgs/${ORG_ID}/clients/c1/export`,
  );
  await user.click(screen.getByRole('button', { name: 'Erase client' }));
  const submit = screen.getByRole('button', { name: /for good/i });
  await user.type(screen.getByLabelText('Type “Mia & Tom” to confirm'), 'Mia');
  expect(submit).toBeDisabled();
  await user.type(screen.getByLabelText('Type “Mia & Tom” to confirm'), ' & Tom');
  await user.click(submit);

  await waitFor(() => expect(router.state.location.pathname).toBe('/app/clients'));
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ confirm: 'Mia & Tom' });
});
