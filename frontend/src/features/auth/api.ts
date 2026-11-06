import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { ApiError, unwrap } from '../../api/problem';
import type { TokenOut, UserOut } from '../../api/types';
import { ensureGuestSession, setAccessToken } from './session';

/** Текущий аккаунт: UserOut или null, если клиент не вошёл (гость). */
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async (): Promise<UserOut | null> => {
      try {
        return unwrap(await api.GET('/api/v1/auth/me'));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60 * 1000,
  });
}

export interface Credentials {
  email: string;
  password: string;
}

/** Вход: по успеху токен попадает в память, профиль — в кэш запросов. */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: Credentials) =>
      unwrap(
        await api.POST('/api/v1/auth/login', {
          body: credentials,
        }),
      ),
    onSuccess: (data: TokenOut) => {
      setAccessToken(data.access_token);
      queryClient.setQueryData(['me'], data.user);
      void queryClient.invalidateQueries({ queryKey: ['me', 'builds'] });
    },
  });
}

/** Регистрация: гостевые сборки на сервере переносятся на новый аккаунт. */
export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: Credentials) =>
      unwrap(
        await api.POST('/api/v1/auth/register', {
          body: credentials,
        }),
      ),
    onSuccess: (data: TokenOut) => {
      setAccessToken(data.access_token);
      queryClient.setQueryData(['me'], data.user);
      void queryClient.invalidateQueries({ queryKey: ['me', 'builds'] });
    },
  });
}

/** Выход: токен забываем, гостевая сессия выдаётся заново, чтобы подбор продолжал работать. */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST('/api/v1/auth/logout');
    },
    onSuccess: async () => {
      setAccessToken(null);
      queryClient.setQueryData(['me'], null);
      queryClient.clear();
      await ensureGuestSession();
    },
  });
}

/** Сохранённые сборки текущего аккаунта для личного кабинета. */
export function useSavedBuilds(enabled: boolean) {
  return useQuery({
    queryKey: ['me', 'builds'],
    queryFn: async () => unwrap(await api.GET('/api/v1/me/builds')),
    enabled,
  });
}
