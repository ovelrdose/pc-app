import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';
import type {
  Category,
  ComponentFrame,
  ComponentOut,
  ComponentPatchIn,
  ComponentStatus,
  FrameOut,
} from '../../api/types';

/** Фильтры списка компонентов админки. */
export interface ComponentFilters {
  category: Category | null;
  brand: string;
  status: ComponentStatus | null;
  source: 'manual' | 'import' | null;
  q: string;
  priceStaleDays: boolean;
  page: number;
}

export const PAGE_SIZE = 25;

/** Схемы фреймов категорий — по ним строятся формы и CSV-подсказки. */
export function useFrames() {
  return useQuery({
    queryKey: ['frames'],
    staleTime: Infinity,
    queryFn: async (): Promise<FrameOut[]> => unwrap(await api.GET('/api/v1/frames')),
  });
}

/** Каталог для админки: список с фильтрами, включая снятые с продажи. */
export function useAdminComponents(filters: ComponentFilters, enabled = true) {
  return useQuery({
    queryKey: ['admin', 'catalog', 'components', filters],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/admin/components', {
          params: {
            query: {
              category: filters.category,
              brand: filters.brand || null,
              status: filters.status,
              source: filters.source,
              q: filters.q || null,
              price_stale_days: filters.priceStaleDays ? 30 : null,
              limit: PAGE_SIZE,
              offset: (filters.page - 1) * PAGE_SIZE,
            },
          },
        }),
      ),
  });
}

/** Карточка компонента для редактирования. */
export function useAdminComponent(componentId: string | undefined) {
  return useQuery({
    queryKey: ['admin', 'catalog', 'component', componentId],
    enabled: componentId !== undefined,
    queryFn: async (): Promise<ComponentOut> =>
      unwrap(
        await api.GET('/api/v1/admin/components/{component_id}', {
          params: { path: { component_id: componentId ?? '' } },
        }),
      ),
  });
}

/** Создать компонент из фрейма категории. */
export function useCreateComponent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ComponentFrame) =>
      unwrap(
        await api.POST('/api/v1/admin/components', {
          body,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'catalog'] });
    },
  });
}

/** Полная замена компонента фреймом категории. */
export function useReplaceComponent(componentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ComponentFrame) =>
      unwrap(
        await api.PUT('/api/v1/admin/components/{component_id}', {
          params: { path: { component_id: componentId } },
          body,
        }),
      ),
    onSuccess: (component: ComponentOut) => {
      queryClient.setQueryData(['admin', 'catalog', 'component', componentId], component);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'catalog'] });
    },
  });
}

/** Служебная правка: наличие, снятие с продажи / возврат к продаже. */
export function usePatchComponent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: ComponentPatchIn }) =>
      unwrap(
        await api.PATCH('/api/v1/admin/components/{component_id}', {
          params: { path: { component_id: id } },
          body: patch,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'catalog'] });
    },
  });
}

/** Импорт CSV одной категории (dry-run или применение). */
export function useCatalogImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      category,
      dryRun,
      file,
    }: {
      category: Category;
      dryRun: boolean;
      file: File;
    }) => {
      const form = new FormData();
      form.append('upload', file);
      return unwrap(
        await api.POST('/api/v1/admin/catalog/import', {
          params: { query: { category, dry_run: dryRun } },
          // Сервер ждёт multipart/form-data; openapi-fetch пропускает FormData как есть.
          body: form as unknown as { upload: string },
        }),
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'catalog'] });
    },
  });
}

/** Скачивает экспорт каталога и сохраняет как `catalog-export.zip`. */
export async function downloadCatalogExport(): Promise<void> {
  const { data, response } = await api.GET('/api/v1/admin/catalog/export', {
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
  link.download = 'catalog-export.zip';
  link.click();
  URL.revokeObjectURL(url);
}

/** Позиции со статусами incomplete/needs_kb и причинами. */
export function useCatalogIssues(
  filters: {
    category: Category | null;
    q: string;
    page: number;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ['admin', 'catalog', 'issues', filters],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/admin/catalog/issues', {
          params: {
            query: {
              category: filters.category,
              q: filters.q || null,
              limit: PAGE_SIZE,
              offset: (filters.page - 1) * PAGE_SIZE,
            },
          },
        }),
      ),
  });
}
