import { Alert, Button, Group, Paper, Stack, Text } from '@mantine/core';
import { IconDeviceFloppy, IconInfoCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';

import { notifyError } from '../../lib/notify';
import { parseYaml, toYaml } from '../../lib/yaml';
import { CodeEditor } from '../../components/CodeEditor';
import { QueryState } from '../../components/QueryState';
import { useReference, useSaveReference } from './api';
import { RegeneratePanel } from './RegeneratePanel';
import { REFERENCE_TITLES } from './referenceLabels';

const HINTS: Record<string, string> = {
  questionnaire:
    'Анкета визарда: шаги с вопросами; вариант ответа может записывать сразу несколько фактов (поле facts). Формат проверяется схемой Questionnaire ядра.',
  golden:
    'Эталонные кейсы: список объектов {id, title, answers, expect}. Прогоняются при проверке и перед публикацией; падение любого кейса блокирует публикацию.',
};

/** YAML-редактор одного справочника: замена целиком с серверной валидацией схемой ядра. */
export function ReferenceEditor({ name }: { name: string }) {
  const reference = useReference(name);
  const save = useSaveReference(name);
  const [yamlText, setYamlText] = useState('');
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Подставляем содержимое справочника при загрузке или смене имени.
  useEffect(() => {
    if (!reference.data || loadedFor === name) return;
    const envelope = reference.data as Record<string, unknown>;
    setYamlText(toYaml('data' in envelope ? envelope.data : envelope));
    setLoadedFor(name);
    setError(null);
  }, [reference.data, name, loadedFor]);

  const doSave = () => {
    const parsed = parseYaml(yamlText);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setError(null);
    save.mutate(parsed.value, {
      onSuccess: () => {
        notifications.show({
          color: 'green',
          title: 'Справочник сохранён',
          message: REFERENCE_TITLES[name] ?? name,
        });
      },
      onError: notifyError,
    });
  };

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          <Group justify="space-between" wrap="wrap">
            <Text size="sm" fw={500}>
              {REFERENCE_TITLES[name] ?? name}{' '}
              <Text span c="dimmed">
                ({name})
              </Text>
            </Text>
            <Button
              size="compact-sm"
              leftSection={<IconDeviceFloppy size={14} />}
              loading={save.isPending}
              onClick={doSave}
            >
              Сохранить
            </Button>
          </Group>
          <Text size="xs" c="dimmed">
            Справочник заменяется целиком: отредактируйте YAML и сохраните. Сервер проверит его
            схемой ядра и покажет ошибки по полям.
          </Text>
          <QueryState isPending={reference.isPending} error={reference.error} />
          {loadedFor === name ? (
            <CodeEditor
              ariaLabel={`Справочник ${REFERENCE_TITLES[name] ?? name} в YAML`}
              language="yaml"
              value={yamlText}
              onChange={(next) => {
                setYamlText(next);
                const parsed = parseYaml(next);
                setError(parsed.ok ? null : parsed.error);
              }}
              height={420}
            />
          ) : null}
          {error ? (
            <Alert color="red" title="Ошибка синтаксиса YAML">
              {error}
            </Alert>
          ) : null}
          {HINTS[name] ? (
            <Alert icon={<IconInfoCircle size={16} />} variant="light" color="gray">
              {HINTS[name]}
            </Alert>
          ) : null}
        </Stack>
      </Paper>
      <RegeneratePanel />
    </Stack>
  );
}
