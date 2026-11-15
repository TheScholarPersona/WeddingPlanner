import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderRoute } from '@/test/render';

describe('LoginPage', () => {
  it('renders an accessible sign-in form in English', () => {
    renderRoute('/login');

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('explains that sign-in is not available yet after submitting', async () => {
    renderRoute('/login');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(screen.getByRole('status')).toHaveTextContent('Sign-in arrives with the next release');
  });

  it('redirects the root path to the login page', () => {
    const { router } = renderRoute('/');

    expect(router.state.location.pathname).toBe('/login');
  });
});
