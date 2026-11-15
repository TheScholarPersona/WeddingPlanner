import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

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
  lead_name: 'Ada Admin',
  my_role: 'lead',
  progress: { done: 0, total: 2, percent: 0 },
  venue_address: null,
  style_notes: null,
  notes_internal: null,
  version: 1,
  open_tasks: 2,
  overdue_tasks: 1,
  client_tasks_open: 1,
  milestones: [],
  team: [
    {
      id: 'pm1',
      membership_id: 'ms1',
      full_name: 'Ada Admin',
      email: 'ada@example.com',
      project_role: 'lead',
    },
  ],
  permissions: ['project:read', 'tasks:read', 'tasks:write', 'comments:write'],
};
const milestones = [
  {
    id: 'm1',
    title: 'Invitations sent',
    due_date: '2027-01-13',
    completed_at: null,
    visibility: 'client',
    position: 0,
    task_total: 2,
    task_done: 0,
  },
];
const task = (over: Record<string, unknown>) => ({
  id: 't1',
  project_id: 'w1',
  milestone_id: 'm1',
  milestone_title: 'Invitations sent',
  title: 'Finalise guest list',
  description: null,
  status: 'open',
  priority: 'normal',
  due_date: '2026-11-01',
  overdue: true,
  assignee_type: 'client',
  assignee_membership_id: null,
  assignee_name: null,
  visibility: 'client',
  completed_at: null,
  completed_by_name: null,
  position: 1,
  version: 4,
  checklist_total: 4,
  checklist_done: 2,
  comment_count: 1,
  ...over,
});
const tasks = [
  task({}),
  task({
    id: 't2',
    title: 'Order printed invitations',
    assignee_type: 'team',
    assignee_name: 'Ada Admin',
    assignee_membership_id: 'ms1',
    visibility: 'internal',
    overdue: false,
    due_date: '2026-12-10',
    checklist_total: 0,
    checklist_done: 0,
    comment_count: 0,
  }),
];

function setup(extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /me': [200, meFixture()],
    [`GET ${P}`]: [200, wedding],
    [`GET ${P}/milestones`]: [200, milestones],
    [`GET ${P}/tasks`]: [200, tasks],
    ...extra,
  });
}

it('groups tasks by milestone and shows who they are for', async () => {
  setup({ [`GET ${P}/tasks?status=open`]: [200, tasks] } as never);
  renderRoute('/app/weddings/w1/tasks');

  const card = (await screen.findByRole('heading', { name: /Invitations sent/ })).closest(
    'section',
  )!;
  const first = within(card).getByText('Finalise guest list').closest('li')!;
  expect(within(first).getByText('Couple')).toBeInTheDocument();
  expect(within(first).getByText('Checklist 2/4 · 1 comment')).toBeInTheDocument();
  expect(within(first).getByText('01.11.2026')).toHaveClass('text-danger');
  expect(within(first).getByText('Shared with couple')).toBeInTheDocument();
  expect(within(card).getByText('Internal')).toBeInTheDocument();
});

it('completes a task from the list', async () => {
  const { calls } = setup({
    [`GET ${P}/tasks?status=open`]: [200, tasks],
    [`POST ${P}/tasks/t2/complete`]: [200, { ...tasks[1], status: 'done', checklist: [] }],
  } as never);
  renderRoute('/app/weddings/w1/tasks');

  await userEvent.click(await screen.findByLabelText('Mark “Order printed invitations” as done'));

  await waitFor(() => expect(calls.some((c) => c.path === `${P}/tasks/t2/complete`)).toBe(true));
});

it('edits a task with its version and posts a comment', async () => {
  const { calls } = setup({
    [`GET ${P}/tasks?status=open`]: [200, tasks],
    [`GET ${P}/tasks/t2`]: [200, { ...tasks[1], checklist: [] }],
    [`GET ${P}/comments?target_type=task&target_id=t2`]: [200, []],
    [`PATCH ${P}/tasks/t2`]: [
      200,
      { ...tasks[1], visibility: 'client', version: 5, checklist: [] },
    ],
    [`POST ${P}/comments`]: [
      201,
      {
        id: 'c1',
        target_type: 'task',
        target_id: 't2',
        author_name: 'Ada Admin',
        is_mine: true,
        body: 'Ordered!',
        visibility: 'internal',
        created_at: '2026-11-15T10:00:00Z',
        edited_at: null,
      },
    ],
  } as never);
  renderRoute('/app/weddings/w1/tasks');

  await userEvent.click(await screen.findByRole('button', { name: /Order printed invitations/ }));
  const dialog = await screen.findByRole('dialog', { name: 'Order printed invitations' });
  await userEvent.selectOptions(within(dialog).getByLabelText('Visibility'), 'client');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
  await userEvent.type(within(dialog).getByLabelText('Write a comment'), 'Ordered!');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Post comment' }));

  const patch = calls.find((c) => c.method === 'PATCH');
  expect(patch?.headers['If-Match']).toBe('"4"');
  expect(patch?.body).toMatchObject({
    visibility: 'client',
    assignee_type: 'team',
    assignee_membership_id: 'ms1',
  });
  await waitFor(() =>
    expect(calls.find((c) => c.path === `${P}/comments` && c.method === 'POST')?.body).toEqual({
      target_type: 'task',
      target_id: 't2',
      body: 'Ordered!',
    }),
  );
});

it('filters tasks for the couple', async () => {
  setup({
    [`GET ${P}/tasks?status=open`]: [200, tasks],
    [`GET ${P}/tasks?assignee=client`]: [200, [tasks[0]]],
  } as never);
  renderRoute('/app/weddings/w1/tasks');

  await userEvent.click(await screen.findByRole('button', { name: 'For the couple' }));

  await waitFor(() =>
    expect(screen.queryByText('Order printed invitations')).not.toBeInTheDocument(),
  );
  expect(screen.getByText('Finalise guest list')).toBeInTheDocument();
});

it('groups my tasks into overdue, this week and later', async () => {
  const today = new Date();
  const iso = (days: number) =>
    new Date(today.getTime() + days * 86_400_000).toISOString().slice(0, 10);
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET /orgs/${ORG_ID}/tasks?status=open`]: [
      200,
      [
        {
          ...task({ id: 'a', title: 'Late one', due_date: iso(-3) }),
          project_title: 'Mia & Tom',
          project_wedding_date: null,
        },
        {
          ...task({ id: 'b', title: 'Soon', due_date: iso(2), overdue: false }),
          project_title: 'Anna & Lukas',
          project_wedding_date: null,
        },
        {
          ...task({ id: 'c', title: 'Someday', due_date: null, overdue: false }),
          project_title: 'Mia & Tom',
          project_wedding_date: null,
        },
      ],
    ],
  } as never);
  renderRoute('/app/tasks');

  const overdue = (await screen.findByRole('heading', { name: 'Overdue' })).closest('section')!;
  expect(within(overdue).getByText('Late one')).toBeInTheDocument();
  const week = screen.getByRole('heading', { name: 'This week' }).closest('section')!;
  expect(within(week).getByRole('link', { name: 'Anna & Lukas' })).toHaveAttribute(
    'href',
    '/app/weddings/w1/tasks',
  );
  expect(screen.getByRole('heading', { name: 'Later' }).closest('section')!).toHaveTextContent(
    'Someday',
  );
});
