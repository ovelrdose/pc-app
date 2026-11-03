import { Alert, Center, Loader } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

import { errorMessage } from '../api/problem';

interface QueryStateProps {
  isPending: boolean;
  error: unknown;
}

/** Индикатор загрузки или сообщение об ошибке запроса. */
export function QueryState({ isPending, error }: QueryStateProps) {
  if (error) {
    return (
      <Alert color="red" icon={<IconAlertTriangle />} title="Не удалось загрузить данные">
        {errorMessage(error)}
      </Alert>
    );
  }
  if (isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }
  return null;
}
