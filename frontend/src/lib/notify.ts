import { notifications } from '@mantine/notifications';

import { errorMessage } from '../api/problem';

/** Уведомление об ошибке действия пользователя. */
export function notifyError(error: unknown): void {
  notifications.show({ color: 'red', title: 'Ошибка', message: errorMessage(error) });
}
