import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';

import { AccountPage } from '@/features/account/AccountPage';
import { AdminLayout, RequireAdmin } from '@/features/admin/AdminLayout';
import { AdminOrganizationsPage } from '@/features/admin/AdminOrganizationsPage';
import { AdminSupportPage } from '@/features/admin/AdminSupportPage';
import { AcceptInvitationPage } from '@/features/auth/AcceptInvitationPage';
import { BudgetPage } from '@/features/budget/BudgetPage';
import { CalendarPage } from '@/features/calendar/CalendarPage';
import { WeddingCalendarPage } from '@/features/calendar/WeddingCalendarPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { RequireClient, RequireTeam } from '@/features/auth/guards';
import { LoginPage } from '@/features/auth/LoginPage';
import { NoAccessPage } from '@/features/auth/NoAccessPage';
import { ResetPasswordPage } from '@/features/auth/ResetPasswordPage';
import { ClientPage } from '@/features/clients/ClientPage';
import { ClientsPage } from '@/features/clients/ClientsPage';
import { DocumentsPage } from '@/features/documents/DocumentsPage';
import {
  MoodboardPage,
  MoodboardsPage,
  PortalBoardPage,
  PortalInspirationPage,
  PortalMorePage,
} from '@/features/moodboards/pages';
import { NotificationsPage } from '@/features/notifications/NotificationsPage';
import { DashboardPage } from '@/features/planner/DashboardPage';
import { PortalBudgetPage } from '@/features/portal/PortalBudgetPage';
import { PortalCalendarPage } from '@/features/portal/PortalCalendarPage';
import { PortalFilesPage } from '@/features/portal/PortalFilesPage';
import { PortalHomePage } from '@/features/portal/PortalHomePage';
import { PortalNotificationsPage } from '@/features/portal/PortalNotificationsPage';
import { PortalPrivacyPage } from '@/features/portal/PortalPrivacyPage';
import { PortalTasksPage } from '@/features/portal/PortalTasksPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { MyTasksPage } from '@/features/tasks/MyTasksPage';
import { WeddingTasksPage } from '@/features/tasks/WeddingTasksPage';
import { TeamPage } from '@/features/team/TeamPage';
import { TemplatePage } from '@/features/templates/TemplatePage';
import { TemplatesPage } from '@/features/templates/TemplatesPage';
import { VendorsPage } from '@/features/vendors/VendorsPage';
import { NewWeddingPage } from '@/features/weddings/NewWeddingPage';
import { WeddingPage } from '@/features/weddings/WeddingPage';
import { WeddingsPage } from '@/features/weddings/WeddingsPage';

import { NotFoundPage } from './NotFoundPage';
import { PlannerLayout } from './PlannerLayout';
import { PortalLayout } from './PortalLayout';

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
      { path: 'weddings', element: <WeddingsPage /> },
      { path: 'weddings/new', element: <NewWeddingPage /> },
      { path: 'weddings/:id', element: <WeddingPage /> },
      { path: 'weddings/:id/tasks', element: <WeddingTasksPage /> },
      { path: 'weddings/:id/budget', element: <BudgetPage /> },
      { path: 'weddings/:id/documents', element: <DocumentsPage /> },
      { path: 'weddings/:id/calendar', element: <WeddingCalendarPage /> },
      { path: 'weddings/:id/moodboards', element: <MoodboardsPage /> },
      { path: 'weddings/:id/moodboards/:boardId', element: <MoodboardPage /> },
      { path: 'calendar', element: <CalendarPage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'account', element: <AccountPage area="app" /> },
      { path: 'tasks', element: <MyTasksPage /> },
      { path: 'clients', element: <ClientsPage /> },
      { path: 'clients/:id', element: <ClientPage /> },
      { path: 'vendors', element: <VendorsPage /> },
      { path: 'templates', element: <TemplatesPage /> },
      { path: 'templates/:id', element: <TemplatePage /> },
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
      { path: 'tasks', element: <PortalTasksPage /> },
      { path: 'budget', element: <PortalBudgetPage /> },
      { path: 'calendar', element: <PortalCalendarPage /> },
      { path: 'files', element: <PortalFilesPage /> },
      { path: 'notifications', element: <PortalNotificationsPage /> },
      { path: 'privacy', element: <PortalPrivacyPage /> },
      { path: 'inspiration', element: <PortalInspirationPage /> },
      { path: 'inspiration/:boardId', element: <PortalBoardPage /> },
      { path: 'more', element: <PortalMorePage /> },
      { path: 'account', element: <AccountPage area="portal" /> },
    ],
  },
  {
    path: '/admin',
    element: (
      <RequireAdmin>
        <AdminLayout />
      </RequireAdmin>
    ),
    children: [
      { index: true, element: <AdminOrganizationsPage /> },
      { path: 'organizations/:id', element: <AdminSupportPage /> },
      { path: 'account', element: <AccountPage area="app" /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
];

export const router = createBrowserRouter(routes);
