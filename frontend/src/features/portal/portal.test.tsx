import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

import { textOn } from './api';

afterEach(() => vi.restoreAllMocks());

const K = '/portal/projects/w1';
const projects = [
  {
    id: 'w1',
    title: 'Mia & Tom',
    wedding_date: '2027-06-12',
    organization: { name: 'Atelier Test', accent_color: '#4F6354' },
  },
];
const portalTask = (over: Record<string, unknown>) => ({
  id: 't1',
  title: 'Finalise guest list',
  description: null,
  status: 'open',
  due_date: '2026-12-01',
  overdue: false,
  milestone_id: 'm1',
  milestone_title: 'Invitations sent',
  for_couple: true,
  checklist: [
    { id: 'c1', title: 'Collect addresses', is_done: true },
    { id: 'c2', title: 'Note diets', is_done: false },
  ],
  comment_count: 0,
  ...over,
});
const me = { ...meFixture('client'), full_name: 'Mia Becker' };

it('shows the countdown, progress and next steps', async () => {
  const { calls } = mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/calendar`]: [
      200,
      [
        {
          kind: 'event',
          id: 'e1',
          title: 'Venue walkthrough',
          date: '2026-12-03',
          end_date: '2026-12-03',
          all_day: false,
          starts_at: '2026-12-03T14:00:00Z',
          ends_at: null,
          location: 'Gut Lindenhof',
          status: null,
          amount_cents: null,
        },
      ],
    ],
    [`GET ${K}`]: [
      200,
      {
        id: 'w1',
        title: 'Mia & Tom',
        wedding_date: '2027-06-12',
        days_to_go: 209,
        venue_name: 'Gut Lindenhof',
        guest_count_planned: 120,
        organization: projects[0]!.organization,
        progress: { done: 4, total: 9, percent: 44 },
        next_steps: [portalTask({})],
        milestones: [
          { id: 'm1', title: 'Invitations sent', due_date: '2027-01-13', completed: false },
        ],
        team: [{ full_name: 'Lena Hoffmann', role: 'lead' }],
        budget: {
          total_cents: 3800000,
          contracted_cents: 2740000,
          paid_cents: 885000,
          currency: 'EUR',
        },
      },
    ],
    [`POST ${K}/tasks/t1/complete`]: [200, []],
  });
  renderRoute('/portal');

  expect(await screen.findByText('209')).toBeInTheDocument();
  expect(screen.getByText('Hi Mia')).toBeInTheDocument();
  expect(screen.getByText('Planning 44 % complete')).toBeInTheDocument();
  expect(screen.getByText(/27\.400,00\s€ of 38\.000,00\s€/)).toBeInTheDocument();
  expect(screen.getByText('Your planners at Atelier Test: Lena Hoffmann')).toBeInTheDocument();
  expect(await screen.findByText('Venue walkthrough')).toBeInTheDocument();

  await userEvent.click(screen.getByLabelText('Mark “Finalise guest list” as done'));
  await waitFor(() => expect(calls.some((c) => c.path === `${K}/tasks/t1/complete`)).toBe(true));
});

it('lets the couple tick only their own tasks', async () => {
  mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/tasks`]: [
      200,
      [
        portalTask({}),
        portalTask({ id: 't2', title: 'Menu tasting', for_couple: false, checklist: [] }),
      ],
    ],
  });
  renderRoute('/portal/tasks');

  expect(await screen.findByLabelText('Mark “Finalise guest list” as done')).toBeEnabled();
  expect(screen.getByLabelText('Mark “Menu tasting” as done')).toBeDisabled();
  expect(screen.getByText('Due 01.12.2026 · 1 of 2 done')).toBeInTheDocument();
  expect(screen.getByText(/Your planner takes care of this/)).toBeInTheDocument();
});

it('shows the shared budget without internal details', async () => {
  mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/budget`]: [
      200,
      {
        total_cents: 3800000,
        currency: 'EUR',
        contracted_cents: 2740000,
        paid_cents: 885000,
        forecast_cents: 3000000,
        categories: [
          {
            id: 'c',
            name: 'Venue',
            items: [
              {
                id: 'i',
                title: 'Gut Lindenhof',
                planned_cents: 1250000,
                quoted_cents: 1250000,
                contracted_cents: 1250000,
                paid_cents: 500000,
                stage: 'booked',
              },
            ],
          },
        ],
        upcoming_payments: [
          {
            id: 'p',
            item_title: 'Catering',
            label: 'Second deposit',
            amount_cents: 200000,
            due_date: '2026-12-15',
            overdue: false,
          },
        ],
      },
    ],
  });
  renderRoute('/portal/budget');

  expect(await screen.findByText(/18\.550,00\s€/)).toBeInTheDocument(); // committed, still to pay
  const venue = screen.getByText('Gut Lindenhof').closest('div')!.parentElement!;
  expect(within(venue).getByText('booked')).toBeInTheDocument();
  expect(screen.getByText('Catering, Second deposit')).toBeInTheDocument();
  expect(screen.queryByText(/internal/i)).not.toBeInTheDocument();
});

describe('textOn', () => {
  it('picks a readable text color for the brand color', () => {
    expect(textOn('#33443A')).toBe('#ffffff');
    expect(textOn('#F5E6C8')).toBe('#1f1d1a');
  });
});

it('shows shared files and lets the couple add one', async () => {
  const doc = (over: Record<string, unknown>) => ({
    id: 'd1',
    title: 'Menu',
    category: 'planning',
    from_couple: false,
    added_by: 'Lena Hoffmann',
    created_at: '2026-11-10T09:00:00Z',
    updated_at: '2026-11-10T09:00:00Z',
    can_delete: false,
    file: {
      filename: 'Menu.pdf',
      content_type: 'application/pdf',
      size_bytes: 1200,
      downloadable: true,
      scan_status: 'clean',
    },
    ...over,
  });
  const { calls } = mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/documents`]: [200, [doc({})]],
    [`POST ${K}/documents`]: [
      201,
      [doc({}), doc({ id: 'd2', title: 'Guest list', from_couple: true, can_delete: true })],
    ],
  });
  const user = userEvent.setup();
  renderRoute('/portal/files');

  const menu = (await screen.findByText('Menu')).closest('li')!;
  expect(within(menu).getByRole('link', { name: 'Download' })).toHaveAttribute(
    'href',
    `/api/v1${K}/documents/d1/download`,
  );
  expect(within(menu).queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Add a file' }));
  await user.upload(
    screen.getByLabelText('File'),
    new File(['a,b'], 'guests.csv', { type: 'text/csv' }),
  );
  await user.type(screen.getByLabelText('Title'), 'Guest list');
  await user.click(screen.getByRole('button', { name: 'Upload document' }));

  await waitFor(() =>
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      file: 'guests.csv',
      title: 'Guest list',
    }),
  );
});

it('lists upcoming appointments in the couple calendar', async () => {
  mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/calendar`]: [
      200,
      [
        {
          kind: 'wedding',
          id: 'w1',
          title: 'Mia & Tom',
          date: '2027-06-12',
          end_date: '2027-06-12',
          all_day: true,
          starts_at: null,
          ends_at: null,
          location: null,
          status: null,
          amount_cents: null,
        },
        {
          kind: 'payment',
          id: 'p1',
          title: 'Venue deposit',
          date: '2027-01-10',
          end_date: '2027-01-10',
          all_day: true,
          starts_at: null,
          ends_at: null,
          location: null,
          status: null,
          amount_cents: 400000,
        },
      ],
    ],
  });

  renderRoute('/portal/calendar');

  expect(await screen.findByText('Your wedding day')).toBeInTheDocument();
  expect(screen.getByText(/Payment 4\.000,00\s€/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add to my calendar' })).toBeInTheDocument();
});

it('lets the couple decide on optional permissions', async () => {
  const { calls } = mockApi({
    'GET /me': [200, me],
    'GET /portal/projects': [200, projects],
    [`GET ${K}/consents`]: [
      200,
      [
        { kind: 'portfolio', granted: null, decided_at: null, outdated: false },
        { kind: 'reviews', granted: null, decided_at: null, outdated: false },
      ],
    ],
    [`PUT ${K}/consents`]: [
      200,
      [
        { kind: 'portfolio', granted: false, decided_at: '2026-11-16T08:00:00Z', outdated: false },
        { kind: 'reviews', granted: null, decided_at: null, outdated: false },
      ],
    ],
  });
  const user = userEvent.setup();
  renderRoute('/portal/privacy');

  const portfolio = await screen.findByRole('group', { name: 'Show our wedding as a reference' });
  await user.click(within(portfolio).getByLabelText('No'));

  await waitFor(() =>
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
      kind: 'portfolio',
      granted: false,
    }),
  );
  expect(await screen.findByText('Your answer from 16.11.2026.')).toBeInTheDocument();
});
