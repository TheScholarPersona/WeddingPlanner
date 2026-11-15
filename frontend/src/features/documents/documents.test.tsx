import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, ORG_ID } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const P = `/orgs/${ORG_ID}/projects/w1`;
const wedding = (permissions: string[]) => ({
  id: 'w1',
  title: 'Mia & Tom',
  permissions: ['project:read', 'documents:read', ...permissions],
});
const version = (over: Record<string, unknown> = {}) => ({
  id: 'v1',
  number: 1,
  filename: 'Venue contract.pdf',
  content_type: 'application/pdf',
  size_bytes: 248_000,
  scan_status: 'clean',
  downloadable: true,
  uploaded_by_name: 'Max Member',
  created_at: '2026-11-10T09:00:00Z',
  ...over,
});
const doc = (over: Record<string, unknown> = {}) => ({
  id: 'd1',
  title: 'Venue contract',
  category: 'contract',
  visibility: 'internal',
  uploaded_by_type: 'team',
  created_by_name: 'Max Member',
  created_at: '2026-11-10T09:00:00Z',
  updated_at: '2026-11-10T09:00:00Z',
  version: 1,
  current: version(),
  version_count: 1,
  ...over,
});

test('lists documents with sharing and scan state', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding([])],
    [`GET ${P}/documents`]: [
      200,
      [
        doc(),
        doc({
          id: 'd2',
          title: 'Moodboard',
          category: 'inspiration',
          visibility: 'client',
          uploaded_by_type: 'client',
          current: version({ id: 'v2', scan_status: 'pending', downloadable: false }),
        }),
      ],
    ],
  });

  renderRoute('/app/weddings/w1/documents');

  const contract = (await screen.findByText('Venue contract')).closest('li')!;
  expect(within(contract).getByText(/Contract · 242 KB/)).toBeInTheDocument();
  expect(within(contract).getByRole('link', { name: 'Download' })).toHaveAttribute(
    'href',
    `/api/v1${P}/documents/d1/download`,
  );
  const moodboard = screen.getByText('Moodboard').closest('li')!;
  expect(within(moodboard).getByText('From the couple')).toBeInTheDocument();
  expect(within(moodboard).getByText('Checking for viruses…')).toBeInTheDocument();
  expect(within(moodboard).queryByRole('link', { name: 'Download' })).not.toBeInTheDocument();
  // Viewers cannot upload.
  expect(screen.queryByRole('button', { name: 'Upload document' })).not.toBeInTheDocument();
});

test('uploads a file with category and sharing', async () => {
  const { calls } = mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding(['documents:write'])],
    [`GET ${P}/documents`]: [200, []],
    [`POST ${P}/documents`]: [201, { ...doc(), versions: [version()] }],
  });
  const user = userEvent.setup();
  renderRoute('/app/weddings/w1/documents');

  await user.click(await screen.findByRole('button', { name: 'Upload document' }));
  const dialog = within(screen.getByRole('dialog'));
  const file = new File(['%PDF-1.7'], 'Menu.pdf', { type: 'application/pdf' });
  await user.upload(dialog.getByLabelText('File'), file);
  await user.selectOptions(dialog.getByLabelText('Category'), 'planning');
  await user.click(dialog.getByLabelText(/Share with the couple/));
  await user.click(dialog.getByRole('button', { name: 'Upload document' }));

  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
  const post = calls.find((c) => c.method === 'POST')!;
  expect(post.body).toEqual({ file: 'Menu.pdf', category: 'planning', visibility: 'client' });
  expect(post.headers['Content-Type']).toBeUndefined();
});

test('rejects files above the size limit before uploading', async () => {
  mockApi({
    'GET /me': [200, meFixture('member')],
    [`GET ${P}`]: [200, wedding(['documents:write'])],
    [`GET ${P}/documents`]: [200, []],
  });
  const user = userEvent.setup();
  renderRoute('/app/weddings/w1/documents');

  await user.click(await screen.findByRole('button', { name: 'Upload document' }));
  const dialog = within(screen.getByRole('dialog'));
  const big = new File(['x'], 'huge.pdf', { type: 'application/pdf' });
  Object.defineProperty(big, 'size', { value: 30 * 1024 * 1024 });
  await user.upload(dialog.getByLabelText('File'), big);

  expect(dialog.getByText('This file is larger than 25 MB.')).toBeInTheDocument();
  expect(dialog.getByRole('button', { name: 'Upload document' })).toBeDisabled();
});
