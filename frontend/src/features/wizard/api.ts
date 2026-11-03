import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';
import type { ConsultationOut } from '../../api/types';
import type { Answers } from './answers';

/** Анкета опубликованной базы знаний. */
export function useQuestionnaire() {
  return useQuery({
    queryKey: ['questionnaire'],
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET('/api/v1/questionnaire')),
  });
}

export interface ConsultationInput {
  answers: Answers;
  ownedComponentIds: string[];
  /** Требования, от которых клиент отказался (уступки компромиссной сборки). */
  waived?: string[];
}

/** Создаёт консультацию и сразу запускает подбор трёх вариантов. */
export function useStartConsultation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ answers, ownedComponentIds, waived = [] }: ConsultationInput) => {
      const body =
        waived.length > 0
          ? { answers, owned_component_ids: ownedComponentIds, waived_requirements: waived }
          : { answers, owned_component_ids: ownedComponentIds };
      const created = unwrap(await api.POST('/api/v1/consultations', { body }));
      return unwrap(
        await api.POST('/api/v1/consultations/{consultation_id}/builds', {
          params: { path: { consultation_id: created.id } },
        }),
      );
    },
    onSuccess: (consultation: ConsultationOut) => {
      queryClient.setQueryData(['consultation', consultation.id], consultation);
    },
  });
}
