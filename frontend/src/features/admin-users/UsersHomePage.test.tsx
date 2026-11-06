import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Notifications } from '@mantine/notifications';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { UsersHomePage } from './UsersHomePage';
import { usersFixture } from '../admin-kb/testing/fixtures';

const meResponse = {
  id: 'u-1',
  email: 'admin@sborshik.local',
  role: 'superadmin',
  created_at: '2026-10-01T12:00:00',
};

function problem(status: number, code: string, title: string, detail: string): Response {
  return Response.json(
    { type: `https://sborshik.local/problems/${code}`, title, status, detail },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

function renderPage() {
  return renderWithProviders(
    <>
      <Notifications />
      <UsersHomePage />
    </>,
  );
}

describe('UsersHomePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает пользователей и шлёт PATCH при смене роли', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/auth\/me$/, () => meResponse),
      route('GET', /\/api\/v1\/admin\/users$/, () => usersFixture),
      route('PATCH', /\/api\/v1\/admin\/users\/u-2$/, () => ({
        ...usersFixture.items[1],
        role: 'catalog_admin',
      })),
    ]);
    renderPage();

    expect(await screen.findByText('engineer@sborshik.local')).toBeInTheDocument();
    expect(screen.getByText('blocked@sborshik.local')).toBeInTheDocument();
    // Своя строка помечена и недоступна для правок.
    expect(screen.getByText(/это вы — свою роль и блокировку менять нельзя/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Роль: admin@sborshik.local' })).toBeDisabled();

    // Меняем роль инженеру знаний.
    const roleSelect = screen.getByRole('textbox', { name: 'Роль: engineer@sborshik.local' });
    await user.click(roleSelect);
    await user.click(await screen.findByRole('option', { name: 'Админ каталога' }));

    await waitFor(() => {
      const patch = api.calls.find((call) => call.method === 'PATCH');
      expect(patch).toBeDefined();
      expect(patch?.body).toEqual({ role: 'catalog_admin' });
    });
  });

  it('блокировка требует подтверждения и отзывает токены', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/auth\/me$/, () => meResponse),
      route('GET', /\/api\/v1\/admin\/users$/, () => usersFixture),
      route('PATCH', /\/api\/v1\/admin\/users\/u-2$/, () => ({
        ...usersFixture.items[1],
        is_active: false,
      })),
    ]);
    renderPage();

    const toggle = await screen.findByRole('switch', { name: 'Активен: engineer@sborshik.local' });
    await user.click(toggle);

    // Без подтверждения PATCH не уходит.
    expect(api.calls.filter((call) => call.method === 'PATCH')).toHaveLength(0);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/все его refresh-токены будут отозваны/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Заблокировать' }));

    await waitFor(() => {
      const patch = api.calls.find((call) => call.method === 'PATCH');
      expect(patch?.body).toEqual({ is_active: false });
    });
  });

  it('409 last-superadmin показывает понятное сообщение и откатывает переключатель', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/auth\/me$/, () => meResponse),
      route('GET', /\/api\/v1\/admin\/users$/, () => usersFixture),
      route('PATCH', /\/api\/v1\/admin\/users\/u-2$/, () =>
        problem(
          409,
          'last-superadmin',
          'Последний активный суперадмин',
          'Нельзя понижать последнего активного суперадмина.',
        ),
      ),
    ]);
    renderPage();

    const roleSelect = await screen.findByRole('textbox', {
      name: 'Роль: engineer@sborshik.local',
    });
    await user.click(roleSelect);
    await user.click(await screen.findByRole('option', { name: 'Суперадмин' }));

    expect(await screen.findByText(/Последний активный суперадмин/)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.calls.filter((call) => call.method === 'PATCH')).toHaveLength(1);
    });
  });
});
