import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const O = `/orgs/${ORG_ID}`;
const summary = {
  id: 'w1',
  title: 'Mia & Tom',
  client_id: 'c1',
  client_name: 'Mia & Tom',
  wedding_date: '2027-06-12',
  days_to_go: 209,
  venue_name: 'Gut Lindenhof',
  guest_count_planned: 120,
  status: 'planning',
  lead_name: 'Ada Admin',
  my_role: 'lead',
  progress: { done: 9, total: 19, percent: 47 },
};
const detail = (permissions: string[], role = 'lead') => ({
  ...summary,
  my_role: role,
  venue_address: null,
  style_notes: 'Garden, sage and ivory',
  notes_internal: null,
  version: 3,
  open_tasks: 10,
  overdue_tasks: 1,
  client_tasks_open: 4,
  milestones: [
    {
      id: 'm1',
      title: 'Venue and date secured',
      due_date: '2026-06-17',
      completed: true,
      visibility: 'client',
      task_total: 4,
      task_done: 4,
    },
    {
      id: 'm2',
      title: 'Invitations sent',
      due_date: '2027-01-13',
      completed: false,
      visibility: 'client',
      task_total: 4,
      task_done: 1,
    },
  ],
  team: [
    {
      id: 'pm1',
      membership_id: 'ms1',
      full_name: 'Ada Admin',
      email: 'ada@example.com',
      project_role: 'lead',
    },
  ],
  permissions,
});

it('shows key figures and upcoming weddings on the dashboard', async () => {
  mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${O}/dashboard`]: [
      200,
      {
        active_weddings: 12,
        weddings_next_6_months: 4,
        tasks_due_this_week: 18,
        tasks_due_this_week_mine: 7,
        overdue_tasks: 3,
        overdue_weddings: 2,
        upcoming: [summary],
      },
    ],
  });
  renderRoute('/app');

  expect((await screen.findByText('Active weddings')).parentElement).toHaveTextContent('12');
  expect(screen.getByText('4 in the next 6 months')).toBeInTheDocument();
  expect(screen.getByText('Across 2 weddings')).toBeInTheDocument();
  const row = screen.getByRole('link', { name: /Mia & Tom/ });
  expect(row).toHaveAttribute('href', '/app/weddings/w1');
  expect(within(row).getByText('209 days')).toBeInTheDocument();
  expect(within(row).getByText('Gut Lindenhof · 120 guests · Lead: Ada Admin')).toBeInTheDocument();
});

it('creates a wedding for a new couple with the default template', async () => {
  const { calls, spy } = mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${O}/clients`]: [200, []],
    [`GET ${O}/templates`]: [
      200,
      [
        {
          id: 't1',
          name: 'Standard wedding',
          description: null,
          is_default: true,
          milestone_count: 6,
          task_count: 19,
        },
      ],
    ],
    [`POST ${O}/projects`]: [201, detail(['project:read'])],
  });
  const { router } = renderRoute('/app/weddings/new');

  await userEvent.type(await screen.findByLabelText("Couple's name"), 'Mia & Tom');
  await userEvent.type(screen.getByLabelText('Wedding date'), '2027-06-12');
  await userEvent.type(screen.getByLabelText('Expected guests'), '120');
  await screen.findByRole('option', { name: 'Standard wedding' });
  spy.mockClear();
  await userEvent.click(screen.getByRole('button', { name: 'Create wedding' }));

  await waitFor(() => expect(router.state.location.pathname).toBe('/app/weddings/w1'));
  expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
    client_id: null,
    new_client_name: 'Mia & Tom',
    wedding_date: '2027-06-12',
    guest_count_planned: 120,
    template_id: 't1',
  });
});

it('lets leads edit details and sends the version it is based on', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${O}/projects/w1`]: [200, detail(['project:read', 'project:update', 'project:archive'])],
    [`GET ${O}/projects/w1/vendors`]: [200, []],
    [`GET ${O}/projects/w1/activity`]: [200, { items: [], next_cursor: null }],
    [`PATCH ${O}/projects/w1`]: [
      200,
      { ...detail(['project:read', 'project:update']), version: 4 },
    ],
  });
  renderRoute('/app/weddings/w1');

  expect(await screen.findByText('Invitations sent')).toBeInTheDocument();
  expect(screen.getByText('1 of 4 tasks')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Edit details' }));
  const dialog = screen.getByRole('dialog', { name: 'Edit details' });
  await userEvent.clear(within(dialog).getByLabelText('Expected guests'));
  await userEvent.type(within(dialog).getByLabelText('Expected guests'), '130');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  const patch = calls.find((c) => c.method === 'PATCH');
  expect(patch?.headers['If-Match']).toBe('"3"');
  expect(patch?.body).toMatchObject({ guest_count_planned: 130 });
});

it('shows viewers the wedding without edit controls', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${O}/projects/w1`]: [200, detail(['project:read', 'project_vendors:read'], 'viewer')],
    [`GET ${O}/projects/w1/vendors`]: [200, []],
    [`GET ${O}/projects/w1/activity`]: [200, { items: [], next_cursor: null }],
  });
  renderRoute('/app/weddings/w1');

  expect(await screen.findByRole('heading', { level: 1, name: 'Mia & Tom' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
});
