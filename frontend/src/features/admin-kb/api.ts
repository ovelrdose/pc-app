import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';
import type {
  KbStatusOut,
  PublishOut,
  RegenerateOut,
  Rule,
  RuleDetailOut,
  RuleKind,
  RuleOrigin,
  RuleOut,
  RulePage,
  RuleTestIn,
  RuleTestOut,
  SnapshotOut,
  UserAdminPage,
  UserPatchIn,
  UserRole,
  ValidateReportOut,
  VocabularyOut,
} from '../../api/types';

export const PAGE_SIZE = 25;

// ---------------------------------------------------------------------------
// Правила
// ---------------------------------------------------------------------------

export interface RuleFilters {
  group: string;
  kind: RuleKind | null;
  origin: RuleOrigin | null;
  enabled: boolean | null;
  q: string;
  page: number;
}

/** Список правил рабочей копии с фильтрами (group/kind/origin/enabled/q). */
export function useRules(filters: RuleFilters) {
  return useQuery({
    queryKey: ['admin', 'kb', 'rules', filters],
    queryFn: async (): Promise<RulePage> =>
      unwrap(
        await api.GET('/api/v1/admin/rules', {
          params: {
            query: {
              group: filters.group || null,
              kind: filters.kind,
              origin: filters.origin,
              enabled: filters.enabled,
              q: filters.q || null,
              limit: PAGE_SIZE,
              offset: (filters.page - 1) * PAGE_SIZE,
            },
          },
        }),
      ),
  });
}

/** Только счётчик правил по фильтру (limit=1, важен total). */
function useRuleCount(enabled: boolean | null) {
  return useQuery({
    queryKey: ['admin', 'kb', 'rules', 'count', enabled],
    queryFn: async (): Promise<number> => {
      const page = unwrap(
        await api.GET('/api/v1/admin/rules', {
          params: { query: { enabled, limit: 1, offset: 0 } },
        }),
      );
      return page.total;
    },
  });
}

/** Статистика черновика: включено / выведено. Общее число правил даёт лёгкий статус (useKbStatus). */
export function useRuleStats() {
  const enabled = useRuleCount(true);
  const retired = useRuleCount(false);
  return { enabled, retired };
}

/** Правило с историей ревизий (редактор). */
export function useRule(code: string | undefined) {
  return useQuery({
    queryKey: ['admin', 'kb', 'rule', code],
    enabled: code !== undefined,
    queryFn: async (): Promise<RuleDetailOut> =>
      unwrap(
        await api.GET('/api/v1/admin/rules/{code}', {
          params: { path: { code: code ?? '' } },
        }),
      ),
  });
}

/** Словарь фактов для конструктора условий. */
export function useVocabulary() {
  return useQuery({
    queryKey: ['admin', 'kb', 'vocabulary'],
    staleTime: 10 * 60 * 1000,
    queryFn: async (): Promise<VocabularyOut[]> =>
      unwrap(await api.GET('/api/v1/admin/kb/vocabulary')),
  });
}

function invalidateKb(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['admin', 'kb'] });
}

/** Создать ручное правило. */
export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Rule): Promise<RuleOut> =>
      unwrap(
        await api.POST('/api/v1/admin/rules', {
          body,
        }),
      ),
    onSuccess: () => invalidateKb(queryClient),
  });
}

/** Полная замена правила (новая ревизия); для сгенерированных — override с предупреждением. */
export function useReplaceRule(code: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Rule): Promise<RuleOut> =>
      unwrap(
        await api.PUT('/api/v1/admin/rules/{code}', {
          params: { path: { code } },
          body,
        }),
      ),
    onSuccess: (rule) => {
      queryClient.setQueryData(['admin', 'kb', 'rule', code], (old: RuleDetailOut | undefined) =>
        old ? { ...old, rule } : old,
      );
      invalidateKb(queryClient);
    },
  });
}

/** Вывести правило из эксплуатации (enabled=false, новая ревизия). */
export function useRetireRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string): Promise<RuleOut> =>
      unwrap(
        await api.POST('/api/v1/admin/rules/{code}/retire', {
          params: { path: { code } },
        }),
      ),
    onSuccess: () => invalidateKb(queryClient),
  });
}

/** Изолированный прямой вывод на заданных фактах; goal-правила дают 422 goal-rule-test-unsupported. */
export function useTestRule(code: string) {
  return useMutation({
    mutationFn: async (input: RuleTestIn): Promise<RuleTestOut> =>
      unwrap(
        await api.POST('/api/v1/admin/rules/{code}/test', {
          params: { path: { code } },
          body: input,
        }),
      ),
  });
}

// ---------------------------------------------------------------------------
// Жизненный цикл: проверка, публикация, снимки, экспорт
// ---------------------------------------------------------------------------

/** Лёгкий статус черновика: контрольная сумма, совпадение со снимком, число правил.
 *  Одно чтение из БД, без компиляции и эталонных кейсов — грузится мгновенно при открытии панели БЗ. */
export function useKbStatus() {
  return useQuery({
    queryKey: ['admin', 'kb', 'status'],
    queryFn: async (): Promise<KbStatusOut> => unwrap(await api.GET('/api/v1/admin/kb/status')),
  });
}

/** Stateless-проверка черновика (§6.2 + golden); ничего не записывает. */
export function useValidateKb() {
  return useMutation({
    mutationFn: async (): Promise<ValidateReportOut> =>
      unwrap(await api.POST('/api/v1/admin/kb/validate')),
  });
}

/** Опубликовать черновик; при ошибках — 409 kb-invalid с findings. */
export function usePublishKb() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (comment: string): Promise<PublishOut> =>
      unwrap(
        await api.POST('/api/v1/admin/kb/publish', {
          params: { query: { comment: comment || null } },
        }),
      ),
    onSuccess: () => invalidateKb(queryClient),
  });
}

/** Опубликованные снимки, новые первыми. */
export function useSnapshots() {
  return useQuery({
    queryKey: ['admin', 'kb', 'snapshots'],
    queryFn: async (): Promise<SnapshotOut[]> =>
      unwrap(await api.GET('/api/v1/admin/kb/snapshots')),
  });
}

/** Откат: повторная публикация выбранного снимка (новая версия). */
export function useRepublishSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (snapshotId: number): Promise<PublishOut> =>
      unwrap(
        await api.POST('/api/v1/admin/kb/snapshots/{snapshot_id}/republish', {
          params: { path: { snapshot_id: snapshotId } },
        }),
      ),
    onSuccess: () => invalidateKb(queryClient),
  });
}

/** Скачивает экспорт знаний и сохраняет как `kb-export.zip`. */
export async function downloadKbExport(): Promise<void> {
  const { data, response } = await api.GET('/api/v1/admin/kb/export', {
    parseAs: 'blob',
  });
  if (data === undefined) {
    unwrap({ response });
  }
  if (!(data instanceof Blob)) {
    throw new Error('Сервер вернул не файл');
  }
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'kb-export.zip';
  link.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Справочники и регенерация
// ---------------------------------------------------------------------------

/** Все справочники, анкета и golden cases рабочей копии: имя → содержимое. */
export function useReferenceList() {
  return useQuery({
    queryKey: ['admin', 'kb', 'reference'],
    queryFn: async (): Promise<Record<string, unknown>> =>
      unwrap(await api.GET('/api/v1/admin/reference')),
  });
}

/** Один справочник по имени. */
export function useReference(name: string | undefined) {
  return useQuery({
    queryKey: ['admin', 'kb', 'reference', name],
    enabled: name !== undefined,
    queryFn: async (): Promise<unknown> =>
      unwrap(
        await api.GET('/api/v1/admin/reference/{name}', {
          params: { path: { name: name ?? '' } },
        }),
      ),
  });
}

/** Заменить справочник целиком (валидация схемами ядра, 422 reference-invalid). */
export function useSaveReference(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: unknown) =>
      unwrap(
        await api.PUT('/api/v1/admin/reference/{name}', {
          params: { path: { name } },
          body: body as Record<string, unknown>,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kb', 'reference'] });
    },
  });
}

/** Перегенерация табличных правил в черновик: сначала предпросмотр (dry_run), затем применение. */
export function useRegenerate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dryRun: boolean): Promise<RegenerateOut> =>
      unwrap(
        await api.POST('/api/v1/admin/reference/regenerate', {
          params: { query: { dry_run: dryRun } },
        }),
      ),
    onSuccess: (_result, dryRun) => {
      if (!dryRun) {
        invalidateKb(queryClient);
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Пользователи
// ---------------------------------------------------------------------------

export interface UserFilters {
  role: UserRole | null;
  q: string;
  isActive: boolean | null;
  page: number;
}

/** Пользователи: список с фильтрами (superadmin). */
export function useUsers(filters: UserFilters) {
  return useQuery({
    queryKey: ['admin', 'users', filters],
    queryFn: async (): Promise<UserAdminPage> =>
      unwrap(
        await api.GET('/api/v1/admin/users', {
          params: {
            query: {
              role: filters.role,
              q: filters.q || null,
              is_active: filters.isActive,
              limit: PAGE_SIZE,
              offset: (filters.page - 1) * PAGE_SIZE,
            },
          },
        }),
      ),
  });
}

/** Сменить роль и/или заблокировать (отзывает токены); 409 для себя и последнего суперадмина. */
export function usePatchUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: UserPatchIn }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/users/{user_id}', {
          params: { path: { user_id: id } },
          body: patch,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}
