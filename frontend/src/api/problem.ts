/** Ошибка API в формате RFC 9457 problem+json. */
export class ApiError extends Error {
  readonly status: number;
  readonly type: string | undefined;
  /** Дополнительные данные проблемы: например `findings` при 409 kb-invalid. */
  readonly findings: string[];

  constructor(status: number, title: string, detail?: string, type?: string, findings?: string[]) {
    super(detail ? `${title}: ${detail}` : title);
    this.name = 'ApiError';
    this.status = status;
    this.type = type;
    this.findings = findings ?? [];
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

function findings(value: unknown): string[] {
  if (typeof value === 'object' && value !== null && 'findings' in value) {
    const raw = (value as Record<string, unknown>).findings;
    if (Array.isArray(raw)) {
      return raw.filter((item): item is string => typeof item === 'string');
    }
  }
  return [];
}

/** Код проблемы из поля `type` вида `https://…/problems/<code>`. */
export function problemCode(error: unknown): string | undefined {
  if (error instanceof ApiError && error.type) {
    return error.type.split('/').pop();
  }
  return undefined;
}

/** Достаёт данные из ответа openapi-fetch или бросает `ApiError` с текстом для пользователя. */
export function unwrap<T>(result: FetchResult<T>): T {
  if (result.error !== undefined || result.data === undefined) {
    const { status } = result.response;
    const title = field(result.error, 'title') ?? 'Сервер не ответил';
    throw new ApiError(
      status,
      title,
      field(result.error, 'detail'),
      field(result.error, 'type'),
      findings(result.error),
    );
  }
  return result.data;
}

/** Текст ошибки для уведомления. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Что-то пошло не так';
}
