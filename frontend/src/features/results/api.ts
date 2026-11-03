import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';

/** Консультация с её сборками. */
export function useConsultation(id: string | undefined) {
  return useQuery({
    queryKey: ['consultation', id],
    enabled: id !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/consultations/{consultation_id}', {
          params: { path: { consultation_id: id ?? '' } },
        }),
      ),
  });
}

/** Разбор невыполнимого запроса (только для консультаций со статусом `infeasible`). */
export function useInfeasible(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['consultation', id, 'infeasible'],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/consultations/{consultation_id}/infeasible', {
          params: { path: { consultation_id: id } },
        }),
      ),
  });
}
