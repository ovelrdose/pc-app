import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { renderWithProviders } from '../../../tests/renderWithProviders';
import { CabinetPage } from '../cabinet/CabinetPage';
import { LoginPage } from './LoginPage';

const LOGIN_URL = `${window.location.origin}/api/v1/auth/login`;

function urlOf(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function renderLogin() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/cabinet" element={<CabinetPage />} />
    </Routes>,
    { route: '/login' },
  );
}

describe('LoginPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('входит по email и паролю и переходит в кабинет', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.startsWith(LOGIN_URL)) {
        return Response.json({
          access_token: 'access-1',
          token_type: 'bearer',
          expires_in: 900,
          user: {
            id: '11111111-1111-1111-1111-111111111111',
            email: 'ivan@example.com',
            role: 'client',
            created_at: '2026-11-03T00:00:00Z',
          },
        });
      }
      if (url.includes('/api/v1/me/builds')) {
        return Response.json({ builds: [], total: 0 });
      }
      return new Response(null, { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderLogin();

    await userEvent.type(screen.getByLabelText('Email'), 'ivan@example.com');
    await userEvent.type(screen.getByLabelText('Пароль'), 'сложный-пароль-123');
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }));

    const loginCall = fetchMock.mock.calls.find(([input]) => urlOf(input).startsWith(LOGIN_URL));
    expect(loginCall).toBeDefined();
    const request = loginCall![0] as Request;
    expect(request.method).toBe('POST');
    expect(await request.clone().json()).toEqual({
      email: 'ivan@example.com',
      password: 'сложный-пароль-123',
    });
    // После входа клиент уходит в кабинет
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Сохранённые сборки' }),
    ).toBeInTheDocument();
  });

  it('не отправляет форму с пустым паролем', async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(
      async () => new Response(null, { status: 404 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderLogin();

    await userEvent.type(screen.getByLabelText('Email'), 'ivan@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByText('Введите пароль')).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([input]) => urlOf(input).startsWith(LOGIN_URL)),
    ).toHaveLength(0);
  });
});
