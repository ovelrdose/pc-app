import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';

import { api } from '../api/client';
import { unwrap } from '../api/problem';
import type { Category } from '../api/types';

const SEARCH_LIMIT = 20;

/** Поиск товаров каталога по названию или SKU (с задержкой ввода). */
export function useComponentSearch(text: string, category?: Category) {
  const [query] = useDebouncedValue(text.trim(), 300);
  return useQuery({
    queryKey: ['components', 'search', query, category ?? null],
    enabled: query.length >= 2,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/components', {
          params: { query: { q: query, category, limit: SEARCH_LIMIT } },
        }),
      ).items,
  });
}
