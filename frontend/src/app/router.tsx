import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';

import { AcceptInvitationPage } from '@/features/auth/AcceptInvitationPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { RequireClient, RequireTeam } from '@/features/auth/guards';
import { LoginPage } from '@/features/auth/LoginPage';
import { NoAccessPage } from '@/features/auth/NoAccessPage';
import { ResetPasswordPage } from '@/features/auth/ResetPasswordPage';
import { ComingSoonPage } from '@/features/planner/ComingSoonPage';
import { DashboardPage } from '@/features/planner/DashboardPage';
import { PortalHomePage } from '@/features/portal/PortalHomePage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { TeamPage } from '@/features/team/TeamPage';

import { NotFoundPage } from './NotFoundPage';
import { PlannerLayout } from './PlannerLayout';
import { PortalLayout } from './PortalLayout';

const comingSoon = ['weddings', 'clients', 'tasks', 'calendar', 'vendors', 'templates'];

export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '/invite/:token', element: <AcceptInvitationPage /> },
  { path: '/no-access', element: <NoAccessPage /> },
  {
    path: '/app',
    element: (
      <RequireTeam>
        <PlannerLayout />
      </RequireTeam>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'team', element: <TeamPage /> },
      { path: 'settings', element: <SettingsPage /> },
      ...comingSoon.map((path) => ({ path, element: <ComingSoonPage /> })),
    ],
  },
  {
    path: '/portal',
    element: (
      <RequireClient>
        <PortalLayout />
      </RequireClient>
    ),
    children: [
      { index: true, element: <PortalHomePage /> },
      ...['tasks', 'budget', 'calendar', 'files'].map((path) => ({
        path,
        element: <ComingSoonPage />,
      })),
    ],
  },
  { path: '*', element: <NotFoundPage /> },
];

export const router = createBrowserRouter(routes);
