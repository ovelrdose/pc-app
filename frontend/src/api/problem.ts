/** Ошибка API в формате RFC 9457 problem+json. */
export class ApiError extends Error {
  readonly status: number;
  readonly type: string | undefined;

  constructor(status: number, title: string, detail?: string, type?: string) {
    super(detail ? `${title}: ${detail}` : title);
    this.name = 'ApiError';
    this.status = status;
    this.type = type;
  }
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

function field(value: unknown, key: string): string | undefined {
  if (typeof value === 'object' && value !== null && key in value) {
    const raw = (value as Record<string, unknown>)[key];
    return typeof raw === 'string' ? raw : undefined;
  }
  return undefined;
}

/** Достаёт данные из ответа openapi-fetch или бросает `ApiError` с текстом для пользователя. */
export function unwrap<T>(result: FetchResult<T>): T {
  if (result.error !== undefined || result.data === undefined) {
    const { status } = result.response;
    const title = field(result.error, 'title') ?? 'Сервер не ответил';
    throw new ApiError(status, title, field(result.error, 'detail'), field(result.error, 'type'));
  }
  return result.data;
}

/** Текст ошибки для уведомления. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Что-то пошло не так';
}
