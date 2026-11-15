import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { isoDate } from '@/lib/format';
import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

import { fromLocalInputs, itemsOn, monthGrid, toLocalInputs, type CalendarItem } from './api';

afterEach(() => vi.restoreAllMocks());

const P = `/orgs/${ORG_ID}/projects/w1`;
const wedding = {
  id: 'w1',
  title: 'Mia & Tom',
  permissions: ['project:read', 'events:write'],
};

describe('calendar helpers', () => {
  test('month grids start on Monday and cover whole weeks', () => {
    const days = monthGrid(new Date(2027, 5, 1)); // June 2027 starts on a Tuesday
    expect(isoDate(days[0]!)).toBe('2027-05-31');
    expect(days.length % 7).toBe(0);
    expect(isoDate(days[days.length - 1]!)).toBe('2027-07-04');
  });

  test('multi-day items show on every day they cover', () => {
    const item = { date: '2027-06-10', end_date: '2027-06-12' } as CalendarItem;
    expect(itemsOn([item], '2027-06-11')).toHaveLength(1);
    expect(itemsOn([item], '2027-06-13')).toHaveLength(0);
  });

  test('local date and time inputs round-trip', () => {
    const iso = fromLocalInputs('2027-06-12', '15:30');
    expect(toLocalInputs(iso)).toEqual({ date: '2027-06-12', time: '15:30' });
  });
});

test('adds an appointment to a wedding', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding],
    [`GET ${P}/events`]: [200, []],
    [`POST ${P}/events`]: [201, {}],
  });
  const user = userEvent.setup();
  renderRoute('/app/weddings/w1/calendar');

  await user.click(await screen.findByRole('button', { name: 'New appointment' }));
  const dialog = within(screen.getByRole('dialog'));
  await user.type(dialog.getByLabelText('Title'), 'Cake tasting');
  await user.clear(dialog.getByLabelText('Date'));
  await user.type(dialog.getByLabelText('Date'), '2027-03-20');
  await user.clear(dialog.getByLabelText('Start'));
  await user.type(dialog.getByLabelText('Start'), '15:00');
  await user.type(dialog.getByLabelText('End'), '16:30');
  await user.type(dialog.getByLabelText('Location'), 'Konditorei Süß');
  await user.click(dialog.getByLabelText(/Show to the couple/));
  await user.click(dialog.getByRole('button', { name: 'Add appointment' }));

  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  expect(calls.find((c) => c.method === 'POST')!.body).toEqual({
    title: 'Cake tasting',
    all_day: false,
    starts_at: fromLocalInputs('2027-03-20', '15:00'),
    ends_at: fromLocalInputs('2027-03-20', '16:30'),
    location: 'Konditorei Süß',
    description: null,
    visibility: 'client',
  });
});

test('shows the month with weddings, appointments, tasks and payments', async () => {
  const today = isoDate(new Date());
  const item = (kind: string, title: string, extra: object = {}) => ({
    kind,
    id: `${kind}-1`,
    title,
    project_id: 'w1',
    project_title: 'Mia & Tom',
    date: today,
    end_date: today,
    all_day: true,
    starts_at: null,
    ends_at: null,
    location: null,
    visibility: 'internal',
    status: null,
    assigned_to_me: false,
    amount_cents: null,
    ...extra,
  });
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET /orgs/${ORG_ID}/calendar`]: [
      200,
      [
        item('wedding', 'Mia & Tom'),
        item('event', 'Cake tasting', {
          all_day: false,
          starts_at: `${today}T14:00:00Z`,
        }),
        item('task', 'Send invitations', { assigned_to_me: true, status: 'open' }),
        item('payment', 'Venue deposit', { amount_cents: 50000 }),
      ],
    ],
  });

  renderRoute('/app/calendar');

  const links = await screen.findAllByRole('link', { name: /Cake tasting/ });
  expect(links[0]).toHaveAttribute('href', '/app/weddings/w1/calendar');
  expect(screen.getAllByRole('link', { name: /Send invitations/ })[0]).toHaveAttribute(
    'href',
    '/app/weddings/w1/tasks?task=task-1',
  );
  expect(screen.getAllByRole('link', { name: /Wedding: Mia & Tom/ }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole('link', { name: /Venue deposit/ }).length).toBeGreaterThan(0);
});

test('creates a private subscription link and shows it once', async () => {
  const feed = `/orgs/${ORG_ID}/calendar/feed`;
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET /orgs/${ORG_ID}/calendar`]: [200, []],
    [`GET ${feed}`]: [200, { active: false, created_at: null, last_used_at: null }],
    [`POST ${feed}`]: [
      201,
      {
        active: true,
        created_at: '2026-11-15T10:00:00Z',
        last_used_at: null,
        url: 'https://localhost/api/v1/calendar-feeds/secret.ics',
      },
    ],
  });
  const user = userEvent.setup();
  renderRoute('/app/calendar');

  await user.click(await screen.findByRole('button', { name: 'Subscribe' }));
  const dialog = within(screen.getByRole('dialog'));
  expect(await dialog.findByText('You have no subscription link yet.')).toBeInTheDocument();
  await user.click(dialog.getByRole('button', { name: 'Create link' }));

  expect(await dialog.findByLabelText('Your private link')).toHaveValue(
    'https://localhost/api/v1/calendar-feeds/secret.ics',
  );
  expect(dialog.getByText(/no notes or amounts/)).toBeInTheDocument();
  expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1);
});
