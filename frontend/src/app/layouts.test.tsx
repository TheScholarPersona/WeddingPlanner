import { screen } from '@testing-library/react';

import { renderRoute } from '@/test/render';

describe('layouts', () => {
  it('shows the planner navigation and dashboard', () => {
    renderRoute('/app');

    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(nav).toHaveTextContent('Dashboard');
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { level: 1, name: 'Good morning' })).toBeInTheDocument();
  });

  it('shows the portal tab bar', () => {
    renderRoute('/portal');

    const nav = screen.getByRole('navigation', { name: 'Portal' });
    for (const label of ['Home', 'Tasks', 'Budget', 'Calendar', 'Files']) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it('shows a not-found page for unknown routes', () => {
    renderRoute('/nowhere');

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });
});
