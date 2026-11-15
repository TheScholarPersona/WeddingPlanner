import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

import { toCents, toInput } from './api';

afterEach(() => vi.restoreAllMocks());

const P = `/orgs/${ORG_ID}/projects/w1`;
const wedding = {
  id: 'w1',
  title: 'Mia & Tom',
  client_id: 'c1',
  client_name: 'Mia & Tom',
  wedding_date: '2027-06-12',
  days_to_go: 209,
  venue_name: null,
  guest_count_planned: null,
  status: 'planning',
  lead_name: null,
  my_role: 'lead',
  progress: { done: 0, total: 0, percent: 0 },
  venue_address: null,
  style_notes: null,
  notes_internal: null,
  version: 1,
  open_tasks: 0,
  overdue_tasks: 0,
  client_tasks_open: 0,
  milestones: [],
  team: [],
  permissions: ['project:read', 'budget:read', 'budget:write', 'budget:set_total'],
};
const item = {
  id: 'i1',
  category_id: 'cat-catering',
  title: 'Küche Feinsinn',
  vendor_id: null,
  vendor_name: null,
  planned_cents: 980000,
  quoted_cents: 920000,
  contracted_cents: 920000,
  internal_cost_cents: 830000,
  paid_by: 'client',
  notes_internal: null,
  visibility: 'client',
  version: 2,
  paid_cents: 200000,
  payments: [],
};
const view = {
  id: 'b1',
  total_cents: 3800000,
  currency: 'EUR',
  warning_threshold_pct: 90,
  version: 3,
  totals: {
    planned_cents: 1270000,
    quoted_cents: 1260000,
    contracted_cents: 920000,
    paid_cents: 200000,
    forecast_cents: 1260000,
    internal_cost_cents: 830000,
    unplanned_cents: 2530000,
  },
  warnings: [{ code: 'quote_above_plan', amount_cents: 50000, item_id: 'i2', title: 'Flowers' }],
  categories: [
    {
      id: 'cat-catering',
      name: 'Catering',
      position: 1,
      planned_cents: 980000,
      forecast_cents: 920000,
      items: [item],
    },
    {
      id: 'cat-flowers',
      name: 'Flowers & Decor',
      position: 2,
      planned_cents: 0,
      forecast_cents: 0,
      items: [],
    },
  ],
  upcoming_payments: [],
};

it('shows totals, warnings and items with internal cost', async () => {
  mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${P}`]: [200, wedding],
    [`GET ${P}/budget`]: [200, view],
    [`GET /orgs/${ORG_ID}/vendors`]: [200, []],
  });
  renderRoute('/app/weddings/w1/budget');

  expect(await screen.findByText(/38\.000,00\s€/)).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(
    'Flowers: the quote is 500,00 € above plan.',
  );
  const row = screen.getByRole('button', { name: 'Küche Feinsinn' }).closest('tr')!;
  expect(within(row).getByText(/8\.300,00\s€/)).toBeInTheDocument();
  expect(within(row).getByText('Visible')).toBeInTheDocument();
});

it('adds an item with the amount in cents', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${P}`]: [200, wedding],
    [`GET ${P}/budget`]: [200, view],
    [`GET /orgs/${ORG_ID}/vendors`]: [200, []],
    [`POST ${P}/budget/items`]: [201, view],
  });
  renderRoute('/app/weddings/w1/budget');

  await userEvent.type(
    await screen.findByLabelText('New item in Flowers & Decor'),
    'Table flowers',
  );
  await userEvent.type(screen.getByLabelText('Planned amount for Flowers & Decor'), '2900.50');
  const flowers = screen.getByRole('heading', { name: 'Flowers & Decor' }).closest('section')!;
  await userEvent.click(within(flowers).getByRole('button', { name: 'Add' }));

  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
    category_id: 'cat-flowers',
    title: 'Table flowers',
    planned_cents: 290050,
  });
});

it('invites the couple from the wedding overview', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${P}`]: [
      200,
      { ...wedding, permissions: [...wedding.permissions, 'client_access:manage'] },
    ],
    [`GET ${P}/vendors`]: [200, []],
    [`GET ${P}/activity`]: [200, { items: [], next_cursor: null }],
    [`GET ${P}/client-access`]: [200, { logins: [], invitations: [] }],
    [`POST ${P}/client-access/invitations`]: [
      201,
      {
        logins: [],
        invitations: [
          {
            id: 'inv',
            email: 'mia@example.com',
            expires_at: '2026-11-22T10:00:00Z',
            expired: false,
          },
        ],
      },
    ],
  });
  renderRoute('/app/weddings/w1');

  await userEvent.type(await screen.findByLabelText('Email of the couple'), 'mia@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Invite' }));

  expect(await screen.findByText('Invited · valid until 22.11.2026')).toBeInTheDocument();
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ email: 'mia@example.com' });
});

describe('money helpers', () => {
  it('converts between euro input and cents', () => {
    expect(toCents('1250,5')).toBe(125050);
    expect(toCents('')).toBeNull();
    expect(toInput(125050)).toBe('1250.50');
    expect(toInput(null)).toBe('');
  });
});
