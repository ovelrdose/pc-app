import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { unwrap } from '../../api/problem';
import type {
  BuildDetail,
  Category,
  HypothesisRequest,
  ModificationRequest,
} from '../../api/types';

const path = (buildId: string) => ({ params: { path: { build_id: buildId } } });

/** Карточка сборки. */
export function useBuild(buildId: string | undefined) {
  return useQuery({
    queryKey: ['build', buildId],
    enabled: buildId !== undefined,
    queryFn: async () => unwrap(await api.GET('/api/v1/builds/{build_id}', path(buildId ?? ''))),
  });
}

/** Сохранить или переименовать сборку. */
export function usePatchBuild(buildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { title?: string | null; is_saved?: boolean | null }) =>
      unwrap(await api.PATCH('/api/v1/builds/{build_id}', { ...path(buildId), body })),
    onSuccess: (build: BuildDetail) => {
      queryClient.setQueryData(['build', buildId], build);
      void queryClient.invalidateQueries({ queryKey: ['consultation', build.consultation_id] });
    },
  });
}

/** Рассуждение и полезность сборки. */
export function useExplanation(buildId: string) {
  return useQuery({
    queryKey: ['build', buildId, 'explanation'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/builds/{build_id}/explanation', path(buildId))),
  });
}

/** Совместимые замены детали категории (`null` — запрос не нужен). */
export function useAlternatives(buildId: string, category: Category | null) {
  return useQuery({
    queryKey: ['build', buildId, 'alternatives', category],
    enabled: category !== null,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/builds/{build_id}/alternatives', {
          params: { path: { build_id: buildId }, query: { category: category ?? 'cpu' } },
        }),
      ),
  });
}

/** «Почему не этот товар?» (`null` — товар не выбран). */
export function useWhyNot(buildId: string, componentId: string | null) {
  return useQuery({
    queryKey: ['build', buildId, 'why-not', componentId],
    enabled: componentId !== null,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/builds/{build_id}/why-not', {
          params: { path: { build_id: buildId }, query: { component_id: componentId ?? '' } },
        }),
      ),
  });
}

/** Правка сборки: новая сборка и разница с прежней. */
export function useModifyBuild(buildId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ModificationRequest) =>
      unwrap(await api.POST('/api/v1/builds/{build_id}/modifications', { ...path(buildId), body })),
    onSuccess: (result) => {
      queryClient.setQueryData(['build', result.build.id], result.build);
      void queryClient.invalidateQueries({
        queryKey: ['consultation', result.build.consultation_id],
      });
    },
  });
}

/** Цели, которые можно проверить обратным выводом. */
export function useGoals() {
  return useQuery({
    queryKey: ['goals'],
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET('/api/v1/goals')),
  });
}

/** Проверка гипотезы «потянет ли». */
export function useHypothesis(buildId: string) {
  return useMutation({
    mutationFn: async (body: HypothesisRequest) =>
      unwrap(await api.POST('/api/v1/builds/{build_id}/hypotheses', { ...path(buildId), body })),
  });
}
