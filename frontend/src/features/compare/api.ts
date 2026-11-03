import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';

/** Сравнение 2–3 сборок. */
export function useCompare(buildIds: string[]) {
  return useQuery({
    queryKey: ['compare', buildIds],
    enabled: buildIds.length >= 2,
    queryFn: async () =>
      unwrap(await api.POST('/api/v1/builds/compare', { body: { build_ids: buildIds } })),
  });
}
