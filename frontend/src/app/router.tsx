import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../components/AppLayout';
import { NotFoundPage } from '../components/NotFoundPage';
import { AdminHomePage } from '../features/admin/AdminHomePage';
import { AdminLayout } from '../features/admin/AdminLayout';
import { RequireRole } from '../features/admin/RequireRole';
import { ADMIN_ROLES, CATALOG_ROLES, KB_ROLES, USERS_ROLES } from '../features/admin/roles';
import { CatalogPage } from '../features/admin-catalog/CatalogPage';
import { ComponentEditPage } from '../features/admin-catalog/ComponentEditPage';
import { ComponentNewPage } from '../features/admin-catalog/ComponentNewPage';
import { CatalogImportPage } from '../features/admin-catalog/ImportPage';
import { IssuesPage } from '../features/admin-catalog/IssuesPage';
import { KbHomePage } from '../features/admin-kb/KbHomePage';
import { ReferencePage } from '../features/admin-kb/ReferencePage';
import { RuleEditorPage } from '../features/admin-kb/RuleEditorPage';
import { RulesPage } from '../features/admin-kb/RulesPage';
import { RuleTestPage } from '../features/admin-kb/RuleTestPage';
import { SnapshotsPage } from '../features/admin-kb/SnapshotsPage';
import { UsersHomePage } from '../features/admin-users/UsersHomePage';
import { BuildPage } from '../features/build/BuildPage';
import { CabinetPage } from '../features/cabinet/CabinetPage';
import { ComparePage } from '../features/compare/ComparePage';
import { HomePage } from '../features/home/HomePage';
import { LoginPage } from '../features/auth/LoginPage';
import { RegisterPage } from '../features/auth/RegisterPage';
import { ResultsPage } from '../features/results/ResultsPage';
import { WizardPage } from '../features/wizard/WizardPage';

export const routes = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'wizard', element: <WizardPage /> },
      { path: 'consultations/:id', element: <ResultsPage /> },
      { path: 'builds/:id', element: <BuildPage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'cabinet', element: <CabinetPage /> },
      {
        path: 'admin',
        element: (
          <RequireRole roles={ADMIN_ROLES}>
            <AdminLayout />
          </RequireRole>
        ),
        children: [
          { index: true, element: <AdminHomePage /> },
          {
            path: 'catalog',
            element: (
              <RequireRole roles={CATALOG_ROLES}>
                <CatalogPage />
              </RequireRole>
            ),
          },
          {
            path: 'catalog/new',
            element: (
              <RequireRole roles={CATALOG_ROLES}>
                <ComponentNewPage />
              </RequireRole>
            ),
          },
          {
            path: 'catalog/import',
            element: (
              <RequireRole roles={CATALOG_ROLES}>
                <CatalogImportPage />
              </RequireRole>
            ),
          },
          {
            path: 'catalog/issues',
            element: (
              <RequireRole roles={CATALOG_ROLES}>
                <IssuesPage />
              </RequireRole>
            ),
          },
          {
            path: 'catalog/:id',
            element: (
              <RequireRole roles={CATALOG_ROLES}>
                <ComponentEditPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb',
            element: (
              <RequireRole roles={KB_ROLES}>
                <KbHomePage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/rules',
            element: (
              <RequireRole roles={KB_ROLES}>
                <RulesPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/rules/new',
            element: (
              <RequireRole roles={KB_ROLES}>
                <RuleEditorPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/rules/:code/test',
            element: (
              <RequireRole roles={KB_ROLES}>
                <RuleTestPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/rules/:code',
            element: (
              <RequireRole roles={KB_ROLES}>
                <RuleEditorPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/snapshots',
            element: (
              <RequireRole roles={KB_ROLES}>
                <SnapshotsPage />
              </RequireRole>
            ),
          },
          {
            path: 'kb/reference',
            element: (
              <RequireRole roles={KB_ROLES}>
                <ReferencePage />
              </RequireRole>
            ),
          },
          {
            path: 'users',
            element: (
              <RequireRole roles={USERS_ROLES}>
                <UsersHomePage />
              </RequireRole>
            ),
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
