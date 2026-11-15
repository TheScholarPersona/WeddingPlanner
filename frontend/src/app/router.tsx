import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';

import { LoginPage } from '@/features/auth/LoginPage';
import { DashboardPage } from '@/features/planner/DashboardPage';
import { PortalHomePage } from '@/features/portal/PortalHomePage';

import { NotFoundPage } from './NotFoundPage';
import { PlannerLayout } from './PlannerLayout';
import { PortalLayout } from './PortalLayout';

export const routes: RouteObject[] = [
  { path: '/', element: <Navigate to="/login" replace /> },
  { path: '/login', element: <LoginPage /> },
  {
    path: '/app',
    element: <PlannerLayout />,
    children: [{ index: true, element: <DashboardPage /> }],
  },
  {
    path: '/portal',
    element: <PortalLayout />,
    children: [{ index: true, element: <PortalHomePage /> }],
  },
  { path: '*', element: <NotFoundPage /> },
];

export const router = createBrowserRouter(routes);
