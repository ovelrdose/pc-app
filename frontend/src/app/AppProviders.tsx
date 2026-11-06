import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';

import { ensureGuestSession } from '../features/auth/session';
import { createQueryClient } from './queryClient';
import { theme } from './theme';

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(createQueryClient);

  // Вкладка открыта без access-токена в памяти: запрашиваем гостевую сессию (HttpOnly-cookie),
  // чтобы подбор и сборки работали до входа в аккаунт.
  useEffect(() => {
    void ensureGuestSession();
  }, []);

  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}
