import { Alert, Badge, Button, Divider, Group, List, Paper, Stack, Text } from '@mantine/core';
import { IconInfoCircle, IconRefresh, IconRefreshAlert } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';

import type { RegenerateOut } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { useRegenerate } from './api';

/** «Перегенерировать»: предпросмотр diff по справочникам, затем применение в черновик. */
export function RegeneratePanel() {
  const regenerate = useRegenerate();
  const [diff, setDiff] = useState<RegenerateOut | null>(null);

  const preview = () => {
    regenerate.mutate(true, { onSuccess: setDiff, onError: notifyError });
  };

  const apply = () => {
    regenerate.mutate(false, {
      onSuccess: (result) => {
        setDiff(result);
        notifications.show({
          color: 'green',
          title: 'Регенерация применена',
          message: `Создано: ${result.created.length}, обновлено: ${result.updated.length}, выведено: ${result.removed.length}`,
        });
      },
      onError: notifyError,
    });
  };

  const totalChanges = diff ? diff.created.length + diff.updated.length + diff.removed.length : 0;

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap">
          <div>
            <Text size="sm" fw={500}>
              Перегенерировать табличные правила
            </Text>
            <Text size="xs" c="dimmed">
              Генератор читает все справочники из рабочей копии и считает разницу с правилами GEN-*
              (origin: generated).
            </Text>
          </div>
          <Group gap="xs">
            <Button
              size="compact-sm"
              variant="light"
              leftSection={<IconRefresh size={14} />}
              loading={regenerate.isPending}
              onClick={preview}
            >
              Предпросмотр (dry-run)
            </Button>
            {diff && totalChanges > 0 ? (
              <Button
                size="compact-sm"
                color="green"
                leftSection={<IconRefreshAlert size={14} />}
                loading={regenerate.isPending}
                onClick={apply}
              >
                Применить
              </Button>
            ) : null}
          </Group>
        </Group>

        <Alert icon={<IconInfoCircle size={16} />} variant="light" color="gray">
          Правила, которые когда-то исправили вручную (стали «ручными», override), не трогаются —
          они перечислены в отчёте отдельно. Новые правила получают первую ревизию, изменённые —
          новую ревизию, выбывшие выключаются. После применения черновик нужно проверить и
          опубликовать.
        </Alert>

        {diff ? (
          <>
            <Divider />
            <Text size="sm" fw={500}>
              {diff.dry_run ? 'Предпросмотр разницы' : 'Применённая разница'}
            </Text>
            <Group gap="md" wrap="wrap">
              <Badge color="green" variant="light">
                + создано: {diff.created.length}
              </Badge>
              <Badge color="yellow" variant="light">
                ~ изменено: {diff.updated.length}
              </Badge>
              <Badge color="red" variant="light">
                − выведено: {diff.removed.length}
              </Badge>
            </Group>
            {totalChanges === 0 ? (
              <Text size="sm" c="dimmed">
                Сгенерированные правила уже соответствуют справочникам — изменений нет.
              </Text>
            ) : (
              <List size="sm" spacing={2}>
                {diff.created.map((code) => (
                  <List.Item key={code}>
                    <Text size="sm">
                      <Badge color="green" variant="light" size="sm">
                        +
                      </Badge>{' '}
                      <code>{code}</code>
                    </Text>
                  </List.Item>
                ))}
                {diff.updated.map((code) => (
                  <List.Item key={code}>
                    <Text size="sm">
                      <Badge color="yellow" variant="light" size="sm">
                        ~
                      </Badge>{' '}
                      <code>{code}</code>
                    </Text>
                  </List.Item>
                ))}
                {diff.removed.map((code) => (
                  <List.Item key={code}>
                    <Text size="sm">
                      <Badge color="red" variant="light" size="sm">
                        −
                      </Badge>{' '}
                      <code>{code}</code> (выключается)
                    </Text>
                  </List.Item>
                ))}
              </List>
            )}
            {diff.overrides.length > 0 ? (
              <Text size="sm" c="dimmed">
                Не тронуты (ручные правки-override): {diff.overrides.join(', ')}
              </Text>
            ) : null}
          </>
        ) : null}
      </Stack>
    </Paper>
  );
}
