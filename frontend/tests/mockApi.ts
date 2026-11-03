import { vi } from 'vitest';

/** Обработчик запроса: тело ответа или `Response` целиком. */
type Handler = (request: Request, match: RegExpMatchArray) => unknown | Promise<unknown>;

export interface MockRoute {
  method: string;
  path: RegExp;
  handler: Handler;
}

export interface MockApi {
  /** Запросы, дошедшие до мока: метод, путь с query и разобранное тело. */
  calls: { method: string; path: string; body: unknown }[];
}

/** Подменяет `fetch` маршрутизатором по методу и пути; неизвестный запрос — 404. */
export function mockApi(routes: MockRoute[]): MockApi {
  const state: MockApi = { calls: [] };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      const text = input.method === 'GET' ? '' : await input.clone().text();
      const body: unknown = text ? JSON.parse(text) : undefined;
      state.calls.push({ method: input.method, path: url.pathname + url.search, body });
      for (const route of routes) {
        const match = url.pathname.match(route.path);
        if (route.method === input.method && match) {
          const result = await route.handler(input, match);
          if (result instanceof Response) return result;
          return Response.json(result, { status: input.method === 'POST' ? 201 : 200 });
        }
      }
      return Response.json(
        { type: 'about:blank', title: 'Не найдено', status: 404 },
        { status: 404, headers: { 'Content-Type': 'application/problem+json' } },
      );
    }),
  );
  return state;
}

export const route = (method: string, path: RegExp, handler: Handler): MockRoute => ({
  method,
  path,
  handler,
});
