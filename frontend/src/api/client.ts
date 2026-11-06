import createClient from 'openapi-fetch';

import type { paths } from './generated/schema';
import { getAccessToken, refreshSession } from '../features/auth/session';

/**
 * Типизированный клиент API; типы генерируются из OpenAPI (`npm run gen:api`).
 * `fetch` берётся при каждом запросе, а не при создании клиента, чтобы его можно было подменить в тестах.
 */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

/** Эндпоинты, где 401 — штатный ответ (не повод обновлять токен и повторять запрос). */
const NO_RETRY_PREFIXES = ['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/auth/refresh'];

api.use({
  onRequest({ request }) {
    const token = getAccessToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    return request;
  },
  async onResponse({ request, response }) {
    const path = new URL(request.url).pathname;
    if (response.status !== 401 || NO_RETRY_PREFIXES.some((p) => path.startsWith(p))) {
      return response;
    }
    // Access-токен протух (или вкладка перезагружена и токен ещё не восстановлен):
    // обновляем по cookie и повторяем запрос один раз.
    if (await refreshSession()) {
      const token = getAccessToken();
      if (token) request.headers.set('Authorization', `Bearer ${token}`);
      return globalThis.fetch(request);
    }
    return response;
  },
});
