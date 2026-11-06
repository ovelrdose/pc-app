import {
  Alert,
  Anchor,
  Button,
  FileButton,
  Group,
  List,
  Paper,
  Select,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconFileCheck, IconFileUpload, IconInfoCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import type { CatalogImportOut, Category } from '../../api/types';
import { CATEGORY_TITLES, CATEGORY_ORDER } from '../../lib/labels';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { useCatalogImport, useFrames } from './api';
import { frameFields } from './frames';
import { STATUS_TITLES } from './labels';

/** Лимит сервера: файлы больше 2 МБ отклоняются (413). */
const MAX_FILE_BYTES = 2 * 1024 * 1024;

/** Импорт CSV: выбор категории и файла, пробный прогон (dry-run) с отчётом, затем применение. */
export function CatalogImportPage() {
  const frames = useFrames();
  const importCsv = useCatalogImport();
  const [category, setCategory] = useState<Category | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);
  const [report, setReport] = useState<CatalogImportOut | null>(null);
  const [applied, setApplied] = useState(false);

  const frame = frames.data?.find((item) => item.category === category) ?? null;
  const fields = useMemo(() => (frame ? frameFields(frame) : []), [frame]);
  // Колонки CSV-шаблона: слоты фрейма (без category и price_kop) + сведения о цене.
  const csvColumns = frame
    ? [
        ...fields
          .filter((f) => f.constValue === undefined && f.name !== 'price_kop')
          .map((f) => f.name),
        'price_rub',
        'price_checked_at',
        'price_note',
      ]
    : [];

  const pickFile = (next: File | null) => {
    setFile(next);
    setReport(null);
    setApplied(false);
    setSizeError(
      next && next.size > MAX_FILE_BYTES
        ? `Файл «${next.name}» больше 2 МБ — сократите файл или разбейте его на части.`
        : null,
    );
  };

  const run = (dryRun: boolean) => {
    if (!category || !file) return;
    importCsv.mutate(
      { category, dryRun, file },
      {
        onSuccess: (result) => {
          setReport(result);
          if (!dryRun) {
            setApplied(true);
            notifications.show({
              color: 'green',
              title: 'Импорт применён',
              message: `Добавлено: ${result.created}, обновлено: ${result.updated}, без изменений: ${result.unchanged}`,
            });
          }
        },
        onError: notifyError,
      },
    );
  };

  const statusCounts = report
    ? Object.entries(report.status_counts).map(([status, count]) => ({
        status,
        count,
      }))
    : [];

  return (
    <Stack gap="md">
      <div>
        <Title order={3}>Импорт каталога из CSV</Title>
        <Text size="sm" c="dimmed">
          Один файл — одна категория. Сначала пробный прогон: база не меняется, показывается отчёт.
          Если всё верно — «Применить».
        </Text>
      </div>

      <QueryState isPending={frames.isPending} error={frames.error} />
      {frames.data ? (
        <Paper withBorder p="lg" radius="md">
          <Stack gap="sm">
            <Select
              label="Категория"
              placeholder="Выберите категорию файла"
              w={320}
              data={CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_TITLES[value] }))}
              value={category}
              onChange={(value) => {
                setCategory((value as Category | null) ?? null);
                setReport(null);
              }}
            />
            <Group>
              <FileButton onChange={pickFile} accept=".csv,text/csv">
                {(props) => (
                  <Button variant="default" leftSection={<IconFileUpload size={16} />} {...props}>
                    Выбрать CSV-файл
                  </Button>
                )}
              </FileButton>
              {file ? (
                <Text size="sm">
                  {file.name} ({Math.ceil(file.size / 1024)} КБ)
                </Text>
              ) : (
                <Text size="sm" c="dimmed">
                  Файл не выбран
                </Text>
              )}
            </Group>
            {sizeError ? (
              <Alert color="red" icon={<IconInfoCircle size={16} />}>
                {sizeError}
              </Alert>
            ) : null}
            <Group>
              <Button
                leftSection={<IconFileCheck size={16} />}
                disabled={!category || !file || sizeError !== null}
                loading={importCsv.isPending}
                onClick={() => run(true)}
              >
                Проверить (dry-run)
              </Button>
              {report && !applied ? (
                <Button
                  color="green"
                  disabled={!category || !file || sizeError !== null}
                  loading={importCsv.isPending}
                  onClick={() => run(false)}
                >
                  Применить
                </Button>
              ) : null}
            </Group>
          </Stack>
        </Paper>
      ) : null}

      {frame ? (
        <Alert icon={<IconInfoCircle size={16} />} variant="light">
          <Text size="sm" fw={500} mb={4}>
            Формат файла для категории «{frame.title}»
          </Text>
          <Text size="sm">
            Кодировка UTF-8, размер до 2 МБ. Первая строка — заголовок с колонками:
            {' ' + csvColumns.join(', ')}. Колонки <code>sku</code>, <code>brand</code>,{' '}
            <code>model</code> и <code>price_rub</code> обязательны; <code>name</code> без колонки
            соберётся из бренда и модели. Списки — через «|», логические — <code>true</code>/
            <code>false</code>, пустая ячейка — «не заполнено». Подробности и примеры — в{' '}
            <code>knowledge/catalog/README.md</code>.
          </Text>
        </Alert>
      ) : null}

      {report ? (
        <Paper withBorder p="lg" radius="md">
          <Title order={4} mb="sm">
            {report.dry_run ? 'Отчёт пробного прогона' : 'Итог импорта'}
          </Title>
          <Group gap="xl" wrap="wrap">
            <Text>
              Добавлено: <b>{report.created}</b>
            </Text>
            <Text>
              Обновлено: <b>{report.updated}</b>
            </Text>
            <Text>
              Без изменений: <b>{report.unchanged}</b>
            </Text>
            <Text size="sm" c="dimmed">
              Ревизия каталога: {report.catalog_revision}
            </Text>
          </Group>
          {statusCounts.length > 0 ? (
            <Text size="sm" mt="xs">
              Статусы после загрузки:{' '}
              {statusCounts
                .map(
                  ({ status, count }) =>
                    `${STATUS_TITLES[status as keyof typeof STATUS_TITLES] ?? status}: ${count}`,
                )
                .join(' · ')}
            </Text>
          ) : null}
          {report.errors.length > 0 ? (
            <Alert color="red" mt="md" title="Отклонённые строки">
              <List size="sm">
                {report.errors.map((error) => (
                  <List.Item key={error}>{error}</List.Item>
                ))}
              </List>
            </Alert>
          ) : (
            <Text size="sm" c="green" mt="md">
              Ошибок формата нет — все строки разобраны.
            </Text>
          )}
          {report.warnings.length > 0 ? (
            <Alert color="yellow" mt="md" title="Предупреждения">
              <List size="sm">
                {report.warnings.map((warning) => (
                  <List.Item key={warning}>{warning}</List.Item>
                ))}
              </List>
            </Alert>
          ) : null}
          <Anchor component={Link} to="/admin/catalog" size="sm" mt="md" display="block">
            К списку компонентов
          </Anchor>
        </Paper>
      ) : null}
    </Stack>
  );
}
