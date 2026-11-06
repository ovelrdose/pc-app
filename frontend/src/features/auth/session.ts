/**
 * Сессия клиента в памяти вкладки: access-токен (JWT) и общий запрос обновления.
 * Refresh-токен и гостевая сессия живут в HttpOnly-cookie, JS их не видит —
 * обновление и выдача гостевой сессии идут через `fetch` с тем же origin.
 */

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Обновляет access-токен по refresh-cookie; повторные вызовы ждут тот же запрос. */
export function refreshSession(): Promise<boolean> {
  refreshPromise ??= (async () => {
    try {
      const response = await globalThis.fetch('/api/v1/auth/refresh', { method: 'POST' });
      if (!response.ok) return false;
      const body = (await response.json()) as { access_token: string };
      accessToken = body.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/** Гарантирует гостевую сессию (cookie) для только что открывшейся вкладки. */
export async function ensureGuestSession(): Promise<void> {
  if (accessToken) return;
  try {
    await globalThis.fetch('/api/v1/sessions/guest', { method: 'POST' });
  } catch {
    // Сеть недоступна: запросы всё равно упадут, повторим при следующем действии.
  }
}
