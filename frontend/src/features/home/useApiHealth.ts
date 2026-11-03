import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';

export function useApiHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/healthz');
      if (error || !data) throw new Error('Сервер недоступен');
      return data;
    },
  });
}
