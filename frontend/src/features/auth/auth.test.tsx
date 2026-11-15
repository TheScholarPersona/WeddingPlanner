import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { meFixture, mockApi, problem } from '@/test/mockApi';
import { renderRoute } from '@/test/render';

import { safeNext } from './session';

afterEach(() => vi.restoreAllMocks());

describe('login', () => {
  it('signs in and opens the planner dashboard', async () => {
    let signedIn = false;
    const { calls } = mockApi({
      'GET /me': () => (signedIn ? [200, meFixture()] : [401, problem(401, 'not_authenticated')]),
      'POST /auth/login': () => {
        signedIn = true;
        return [200, meFixture()];
      },
    });
    const { router } = renderRoute('/login');

    await userEvent.type(await screen.findByLabelText('Email'), 'ada@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Good morning, Ada' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/app');
    expect(calls.find((c) => c.path === '/auth/login')?.body).toEqual({
      email: 'ada@example.com',
      password: 'correct horse battery',
    });
  });

  it('shows a clear message when the credentials are wrong', async () => {
    mockApi({
      'GET /me': [401, problem(401, 'not_authenticated')],
      'POST /auth/login': [401, problem(401, 'invalid_credentials')],
    });
    renderRoute('/login');

    await userEvent.type(await screen.findByLabelText('Email'), 'ada@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The email or password is incorrect.',
    );
  });
});

describe('route guards', () => {
  it('sends anonymous visitors to the login page and remembers where they wanted to go', async () => {
    mockApi({ 'GET /me': [401, problem(401, 'not_authenticated')] });
    const { router } = renderRoute('/app/team');

    await screen.findByRole('heading', { name: 'Welcome back' });
    expect(router.state.location.pathname).toBe('/login');
    expect(router.state.location.search).toBe('?next=%2Fapp%2Fteam');
  });

  it('keeps clients out of the planner app', async () => {
    mockApi({ 'GET /me': [200, meFixture('client')] });
    const { router } = renderRoute('/app');

    await screen.findByRole('navigation', { name: 'Portal' });
    expect(router.state.location.pathname).toBe('/portal');
  });

  it('shows the planner navigation with the organization and sign-out', async () => {
    mockApi({ 'GET /me': [200, meFixture('member')] });
    renderRoute('/app');

    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(nav).toHaveTextContent('Atelier Test');
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });
});

describe('accept invitation', () => {
  it('asks new users for their name and a password', async () => {
    mockApi({
      'GET /auth/invitations/abc': [
        200,
        {
          organization_name: 'Atelier Test',
          email: 'new@example.com',
          role: 'member',
          account_exists: false,
        },
      ],
    });
    renderRoute('/invite/abc');

    expect(await screen.findByLabelText('Full name')).toBeRequired();
    expect(screen.getByLabelText('Choose a password')).toHaveAttribute('minlength', '12');
    expect(screen.getByRole('button', { name: 'Join Atelier Test' })).toBeInTheDocument();
  });

  it('explains when an invitation is no longer valid', async () => {
    mockApi({ 'GET /auth/invitations/old': [404, problem(404, 'invitation_invalid')] });
    renderRoute('/invite/old');

    expect(await screen.findByRole('alert')).toHaveTextContent('Ask for a new invitation.');
  });
});

describe('safeNext', () => {
  it('only allows same-site relative paths', () => {
    expect(safeNext('/app/team')).toBe('/app/team');
    expect(safeNext('//evil.example')).toBeNull();
    expect(safeNext('https://evil.example')).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});

describe('forgot password', () => {
  it('confirms without revealing whether the account exists', async () => {
    mockApi({ 'POST /auth/password/forgot': [202] });
    renderRoute('/forgot-password');

    await userEvent.type(screen.getByLabelText('Email'), 'someone@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('If an account exists'),
    );
  });
});
