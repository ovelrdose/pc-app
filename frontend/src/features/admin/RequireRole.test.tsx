import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import type { UserOut } from '../../api/types';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { RequireRole } from './RequireRole';

function renderGuard(role: UserRole) {
  const me: UserOut = { id: 'u1', email: 'admin@example.com', role, created_at: '2026-11-05' };
  return mockApi([route('GET', /\/auth\/me$/, () => me)]);
}

type UserRole = UserOut['role'];

function tree() {
  return (
    <Routes>
      <Route path="/login" element={<div>страница входа</div>} />
      <Route
        path="/admin/x"
        element={
          <RequireRole roles={['catalog_admin']}>
            <div>секретный раздел</div>
          </RequireRole>
        }
      />
    </Routes>
  );
}

describe('RequireRole', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('пускает пользователя с нужной ролью', async () => {
    renderGuard('catalog_admin');
    renderWithProviders(tree(), { route: '/admin/x' });
    expect(await screen.findByText('секретный раздел')).toBeInTheDocument();
  });

  it('показывает экран «нет доступа», если роль не подходит', async () => {
    renderGuard('knowledge_engineer');
    renderWithProviders(tree(), { route: '/admin/x' });
    expect(await screen.findByText('Нет доступа к разделу')).toBeInTheDocument();
    expect(screen.queryByText('секретный раздел')).not.toBeInTheDocument();
  });

  it('отправляет гостя на вход', async () => {
    mockApi([
      route('GET', /\/auth\/me$/, () =>
        Response.json(
          { type: 'about:blank', title: 'Не авторизован', status: 401 },
          { status: 401, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    ]);
    renderWithProviders(tree(), { route: '/admin/x' });
    await waitFor(() => expect(screen.getByText('страница входа')).toBeInTheDocument());
    expect(screen.queryByText('секретный раздел')).not.toBeInTheDocument();
  });
});
