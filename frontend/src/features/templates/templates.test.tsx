import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { describeOffset } from '@/lib/format';
import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const template = {
  id: 't1',
  name: 'Standard wedding',
  description: null,
  is_default: true,
  milestone_count: 1,
  task_count: 1,
  items: [
    {
      id: 'm1',
      kind: 'milestone',
      title: 'Invitations sent',
      description: null,
      offset_days: -150,
      assignee_type: 'team',
      visibility: 'client',
      parent_item_id: null,
      position: 0,
    },
    {
      id: 'k1',
      kind: 'task',
      title: 'Finalise guest list',
      description: null,
      offset_days: -196,
      assignee_type: 'client',
      visibility: 'client',
      parent_item_id: 'm1',
      position: 1,
    },
  ],
};

it('adds a task to a milestone, converting weeks to days', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture()],
    [`GET /orgs/${ORG_ID}/templates/t1`]: [200, template],
    [`POST /orgs/${ORG_ID}/templates/t1/items`]: [201, template.items[1]],
  });
  renderRoute('/app/templates/t1');

  const card = (await screen.findByRole('heading', { name: 'Invitations sent' })).closest(
    'section',
  )!;
  expect(within(card).getByText('Finalise guest list')).toBeInTheDocument();
  expect(within(card).getByText('28 weeks before · For the couple')).toBeInTheDocument();
  await userEvent.type(within(card).getByLabelText('New task'), 'Order invitations');
  const weeks = within(card).getByRole('spinbutton');
  await userEvent.clear(weeks);
  await userEvent.type(weeks, '20');
  await userEvent.click(within(card).getByRole('button', { name: 'Add' }));

  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
    kind: 'task',
    title: 'Order invitations',
    offset_days: -140,
    parent_item_id: 'm1',
  });
});

it('is read-only for planners', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET /orgs/${ORG_ID}/templates/t1`]: [200, template],
  });
  renderRoute('/app/templates/t1');

  expect(await screen.findByText('Finalise guest list')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
});

describe('describeOffset', () => {
  it('describes offsets in readable units', () => {
    expect(describeOffset(0)).toBe('On the wedding day');
    expect(describeOffset(-360)).toBe('12 months before');
    expect(describeOffset(-28)).toBe('4 weeks before');
    expect(describeOffset(-10)).toBe('10 days before');
    expect(describeOffset(1)).toBe('1 day after');
  });
});
