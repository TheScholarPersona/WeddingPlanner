import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, problem } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

afterEach(() => vi.restoreAllMocks());

const me = { ...meFixture('member'), two_factor_enabled: false, is_platform_admin: false };

test('signing in with two-factor authentication asks for the code', async () => {
  const { calls } = mockApi({
    'GET /me': [401, problem(401, 'not_authenticated')],
    'POST /auth/login': [200, { two_factor_required: true }],
    'POST /auth/2fa/verify': (body) =>
      (body as { code: string }).code === '123456'
        ? [200, me]
        : [400, problem(400, 'invalid_code', 'Code not valid')],
  });
  const user = userEvent.setup();
  renderRoute('/login');

  await user.type(await screen.findByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'correct horse battery staple');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));

  const code = await screen.findByLabelText('Authentication code');
  await user.type(code, '000000');
  await user.click(screen.getByRole('button', { name: 'Verify' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('The code is not valid');

  await user.clear(code);
  await user.type(code, '123456');
  await user.click(screen.getByRole('button', { name: 'Verify' }));
  await waitFor(() => expect(calls.filter((c) => c.path === '/auth/2fa/verify')).toHaveLength(2));
});

test('turning on two-factor authentication shows the QR code and recovery codes once', async () => {
  const { calls } = mockApi({
    'GET /me': [200, me],
    'GET /me/2fa': [200, { enabled: false, enabled_at: null, recovery_codes_left: 0 }],
    'POST /me/2fa/setup': [
      200,
      {
        secret: 'JBSWY3DPEHPK3PXP',
        otpauth_uri: 'otpauth://totp/x',
        qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+',
      },
    ],
    'POST /me/2fa/enable': [200, { recovery_codes: ['abcde-fghjk', 'mnpqr-stuvw'] }],
  });
  const user = userEvent.setup();
  renderRoute('/app/account');

  const card = (await screen.findByRole('heading', { name: 'Two-factor authentication' })).closest(
    'div.flex-col',
  ) as HTMLElement;
  await user.click(within(card).getByRole('button', { name: 'Turn on' }));
  expect(await screen.findByAltText('QR code for your authenticator app')).toBeInTheDocument();
  expect(screen.getByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument();
  await user.type(screen.getByLabelText('Code from the app'), '654321');
  await user.click(screen.getByRole('button', { name: 'Turn on' }));

  const codes = await screen.findByRole('list', { name: 'Recovery codes' });
  expect(
    within(codes)
      .getAllByRole('listitem')
      .map((li) => li.textContent),
  ).toEqual(['abcde-fghjk', 'mnpqr-stuvw']);
  expect(calls.find((c) => c.path === '/me/2fa/enable')!.body).toEqual({ code: '654321' });
});

test('setup asks for the password first when the last confirmation is too old', async () => {
  let confirmed = false;
  mockApi({
    'GET /me': [200, me],
    'GET /me/2fa': [200, { enabled: false, enabled_at: null, recovery_codes_left: 0 }],
    'POST /auth/reauth': () => {
      confirmed = true;
      return [204];
    },
    'POST /me/2fa/setup': () =>
      confirmed
        ? [200, { secret: 'SECRETKEY', otpauth_uri: 'otpauth://totp/x', qr_svg: 'data:,' }]
        : [403, problem(403, 'reauth_required')],
  });
  const user = userEvent.setup();
  renderRoute('/app/account');

  await user.click(await screen.findByRole('button', { name: 'Turn on' }));
  const dialog = within(await screen.findByRole('dialog'));
  await user.type(dialog.getByLabelText('Password'), 'correct horse battery staple');
  await user.click(dialog.getByRole('button', { name: 'Confirm' }));

  expect(await screen.findByText('SECRETKEY')).toBeInTheDocument();
});
