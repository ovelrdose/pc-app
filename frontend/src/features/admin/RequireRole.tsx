import { Center, Loader } from '@mantine/core';
import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useMe } from '../auth/api';
import { AccessDeniedPage } from './AccessDeniedPage';
import type { UserRole } from '../../api/types';

interface RequireRoleProps {
  roles: readonly UserRole[];
  children: ReactNode;
}

/**
 * Guard маршрутов админки: гость уходит на вход, чужая роль — на экран «нет доступа».
 * Роль читается из `useMe` (кэш `GET /auth/me`).
 */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  if (!me.data) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }
  if (!roles.includes(me.data.role)) {
    return <AccessDeniedPage />;
  }
  return <>{children}</>;
}
