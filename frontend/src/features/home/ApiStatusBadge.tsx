import { Badge } from '@mantine/core';

import { useApiHealth } from './useApiHealth';

export function ApiStatusBadge() {
  const { isPending, isError } = useApiHealth();

  if (isPending) return <Badge color="gray">Проверяем сервер…</Badge>;
  if (isError) return <Badge color="red">Сервер недоступен</Badge>;
  return <Badge color="teal">Сервер на связи</Badge>;
}
