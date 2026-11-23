import { screen } from '@testing-library/react';

import { meFixture, mockApi } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const admin = {
  ...meFixture('member'),
  memberships: [],
  is_platform_admin: true,
  two_factor_enabled: true,
};

test('platform admins see organizations with numbers only', async () => {
  mockApi({
    'GET /me': [200, admin],
    'GET /admin/organizations': [
      200,
      [
        {
          id: 'o1',
          name: 'Atelier Lumière',
          slug: 'atelier',
          status: 'active',
          created_at: '2026-11-01T10:00:00Z',
          require_2fa: false,
          members: 3,
          clients: 5,
          support_until: '2026-11-20T10:00:00Z',
        },
      ],
    ],
  });

  renderRoute('/admin');

  expect(await screen.findByText('Atelier Lumière')).toBeInTheDocument();
  expect(screen.getByText('Support until 20.11.2026')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute(
    'href',
    '/admin/organizations/o1',
  );
  expect(screen.getByRole('button', { name: 'Suspend' })).toBeInTheDocument();
});

test('the admin area is not shown to other users', async () => {
  mockApi({
    'GET /me': [200, { ...meFixture('member'), is_platform_admin: false }],
    'GET /orgs/0193a1c2-0000-7000-8000-000000000001/dashboard': [404, {}],
  });

  const { router } = renderRoute('/admin');

  await vi.waitFor(() => expect(router.state.location.pathname).not.toBe('/admin'));
});

test('the support view shows team, weddings and audit log read-only', async () => {
  mockApi({
    'GET /me': [200, admin],
    'GET /admin/organizations/o1/support': [
      200,
      {
        organization: { id: 'o1', name: 'Atelier Lumière' },
        grant_expires_at: '2026-11-20T10:00:00Z',
        members: [
          {
            email: 'lena@example.com',
            full_name: 'Lena Hoffmann',
            role: 'org_admin',
            status: 'active',
            two_factor_enabled: false,
          },
        ],
        weddings: [
          { id: 'w1', title: 'Mia & Tom', wedding_date: '2027-06-12', status: 'active', team: 2 },
        ],
        audit: [
          {
            action: 'support.viewed',
            actor_name: 'Platform Support',
            actor_type: 'user',
            created_at: '2026-11-18T09:30:00Z',
          },
        ],
      },
    ],
  });

  renderRoute('/admin/organizations/o1');

  expect(await screen.findByRole('heading', { name: 'Atelier Lumière' })).toBeInTheDocument();
  expect(screen.getByText('Read-only support access until 20.11.2026')).toBeInTheDocument();
  expect(screen.getByText('Lena Hoffmann')).toBeInTheDocument();
  expect(screen.getByText('No 2FA')).toBeInTheDocument();
  expect(screen.getByText('Mia & Tom')).toBeInTheDocument();
  expect(screen.getByText('support.viewed')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /save|delete|edit/i })).not.toBeInTheDocument();
});
