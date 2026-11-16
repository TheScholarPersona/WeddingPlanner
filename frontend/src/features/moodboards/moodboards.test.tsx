import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const P = `/orgs/${ORG_ID}/projects/w1`;
const MB = `${P}/moodboards`;
const wedding = (permissions: string[]) => ({
  id: 'w1',
  title: 'Mia & Tom',
  permissions: ['project:read', 'moodboards:read', ...permissions],
});
const item = (over: Record<string, unknown> = {}) => ({
  id: 'i1',
  section_id: 's-flowers',
  caption: 'Peonies in blush',
  status: 'proposed',
  width: 1200,
  height: 900,
  ready: true,
  scan_status: 'clean',
  uploaded_by_name: 'Lena Hoffmann',
  uploaded_by_type: 'team',
  can_edit: true,
  hearts: 1,
  hearted_by_me: false,
  heart_names: ['Mia Becker'],
  comment_count: 0,
  created_at: '2026-11-16T09:00:00Z',
  ...over,
});
const board = (over: Record<string, unknown> = {}) => ({
  id: 'b1',
  title: 'Overall look',
  visibility: 'client',
  created_by_type: 'team',
  palette: ['#c9a9a6', '#4f6354'],
  item_count: 2,
  selected_count: 0,
  preview: ['i1'],
  updated_at: '2026-11-16T09:00:00Z',
  version: 3,
  notes_internal: null,
  sections: [
    { id: 's-flowers', title: 'Flowers' },
    { id: 's-cake', title: 'Cake' },
  ],
  items: [
    item(),
    item({ id: 'i2', caption: null, section_id: 's-cake', hearts: 0, heart_names: [] }),
  ],
  can_manage: true,
  can_delete: true,
  ...over,
});

test('lists boards with previews and sharing state', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding(['moodboards:write'])],
    [`GET ${MB}`]: [200, [{ ...board(), sections: undefined, items: undefined }]],
  });

  renderRoute('/app/weddings/w1/moodboards');

  const card = (await screen.findByText('Overall look')).closest('a')!;
  expect(card).toHaveAttribute('href', '/app/weddings/w1/moodboards/b1');
  expect(within(card).getByText('Shared with couple')).toBeInTheDocument();
  expect(within(card).getByText('2 images · 0 selected')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'New board' })).toBeInTheDocument();
});

test('the planner selects an image in the large view', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding(['moodboards:write'])],
    [`GET ${MB}/b1`]: [200, board()],
    [`GET ${P}/comments`]: [200, []],
    [`PATCH ${MB}/b1/items/i1`]: [
      200,
      board({ items: [item({ status: 'selected' })], selected_count: 1 }),
    ],
    [`GET ${MB}`]: [200, []],
  });
  const user = userEvent.setup();
  renderRoute('/app/weddings/w1/moodboards/b1');

  expect(await screen.findByRole('heading', { name: 'Flowers' })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Image in Cake' })).toHaveAttribute(
    'src',
    `/api/v1${MB}/b1/items/i2/image?size=thumb`,
  );
  await user.click(screen.getByRole('button', { name: 'Open Peonies in blush' }));
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByText('Hearted by Mia Becker')).toBeInTheDocument();
  await user.click(dialog.getByRole('button', { name: 'Selected' }));

  await waitFor(() =>
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ status: 'selected' }),
  );
  expect(screen.getByRole('link', { name: 'PDF: selected' })).toHaveAttribute(
    'href',
    `/api/v1${MB}/b1/export.pdf?selected_only=true`,
  );
});

test('uploads several images into a section', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding(['moodboards:write'])],
    [`GET ${MB}/b1`]: [200, board()],
    [`POST ${MB}/b1/items`]: [201, board()],
    [`GET ${MB}`]: [200, []],
  });
  const user = userEvent.setup();
  renderRoute('/app/weddings/w1/moodboards/b1');

  const input = await screen.findByLabelText('Add images to Cake');
  await user.upload(input, [
    new File(['a'], 'cake-1.jpg', { type: 'image/jpeg' }),
    new File(['b'], 'cake-2.jpg', { type: 'image/jpeg' }),
  ]);

  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  expect(calls.find((c) => c.method === 'POST')!.body).toEqual({
    files: 'cake-2.jpg',
    section_id: 's-cake',
  });
});

test('couples heart and comment but do not decide', async () => {
  const K = '/portal/projects/w1/moodboards';
  const { calls } = mockApi({
    'GET /me': [200, meFixture('client')],
    'GET /portal/projects': [
      200,
      [
        {
          id: 'w1',
          title: 'Mia & Tom',
          wedding_date: null,
          organization: { name: 'Atelier', accent_color: null },
        },
      ],
    ],
    [`GET ${K}/b1`]: [
      200,
      {
        ...board({ can_manage: false, can_delete: false, items: [item({ can_edit: false })] }),
        from_couple: false,
      },
    ],
    [`GET ${K}/b1/items/i1/comments`]: [200, []],
    [`PUT ${K}/b1/items/i1/heart`]: [200, { ...board(), from_couple: false }],
    [`POST ${K}/b1/items/i1/comments`]: [201, {}],
    [`GET ${K}`]: [200, []],
  });
  const user = userEvent.setup();
  renderRoute('/portal/inspiration/b1');

  await user.click(await screen.findByRole('button', { name: 'Open Peonies in blush' }));
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.queryByRole('button', { name: 'Selected' })).not.toBeInTheDocument();
  expect(dialog.queryByRole('button', { name: 'Delete image' })).not.toBeInTheDocument();
  await user.click(dialog.getByRole('button', { name: 'Heart' }));
  await user.type(dialog.getByLabelText('Write a comment'), 'Love these!');
  await user.click(dialog.getByRole('button', { name: 'Send' }));

  await waitFor(() =>
    expect(
      calls.find((c) => c.path === `${K}/b1/items/i1/comments` && c.method === 'POST')?.body,
    ).toEqual({
      body: 'Love these!',
    }),
  );
  expect(calls.some((c) => c.method === 'PUT')).toBe(true);
  expect(screen.queryByRole('link', { name: 'PDF: selected' })).not.toBeInTheDocument();
});
