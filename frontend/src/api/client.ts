import createClient from 'openapi-fetch';

import type { paths } from './generated/schema';

/**
 * Типизированный клиент API; типы генерируются из OpenAPI (`npm run gen:api`).
 * `fetch` берётся при каждом запросе, а не при создании клиента, чтобы его можно было подменить в тестах.
 */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => globalThis.fetch(request),
});
