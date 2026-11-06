import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconChecklist,
  IconDatabaseExport,
  IconFiles,
  IconPackages,
  IconRocket,
  IconTable,
} from '@tabler/icons-react';
import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { problemCode, ApiError } from '../../api/problem';
import type { ValidateReportOut } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { downloadKbExport, useKbStatus, usePublishKb, useRuleStats, useValidateKb } from './api';
import { ValidateReport } from './ValidateReport';

/** Панель состояния базы знаний: черновик vs опубликованный снимок, проверка, публикация. */
export function KbHomePage() {
  const stats = useRuleStats();
  const status = useKbStatus();
  const validate = useValidateKb();
  const publish = usePublishKb();
  const [report, setReport] = useState<ValidateReportOut | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [comment, setComment] = useState('');
  const validateGuard = useRef(false);

  // При открытии грузится только лёгкий статус (TanStack Query сам дедуплицирует повторные
  // запросы в StrictMode). Полная проверка черновика — только по кнопке «Проверить».
  const runValidate = () => {
    // Guard-ref: защита от повторного запуска, пока идёт текущая проверка (двойной клик).
    if (validateGuard.current) return;
    validateGuard.current = true;
    validate.mutate(undefined, {
      onSuccess: (next) => {
        setReport(next);
        notifications.show({
          color: next.errors.length > 0 ? 'red' : next.warnings.length > 0 ? 'yellow' : 'green',
          title: 'Проверка завершена',
          message: `Ошибок: ${next.errors.length}, предупреждений: ${next.warnings.length}`,
        });
      },
      onError: notifyError,
      onSettled: () => {
        validateGuard.current = false;
      },
    });
  };

  const doPublish = () => {
    publish.mutate(comment, {
      onSuccess: (result) => {
        setPublishOpen(false);
        setComment('');
        notifications.show({
          color: 'green',
          title: result.created ? `Опубликован снимок v${result.version}` : 'Снимок не создан',
          message: result.created
            ? `Правил: ${result.rules}, предупреждений: ${result.warnings}, эталонных кейсов: ${result.golden_cases}, статусов пересчитано: ${result.statuses_changed}`
            : 'Черновик совпадает с последним опубликованным снимком — новая версия не нужна.',
        });
        // Статус (checksum/matches_latest) обновится сам: публикация снимает кэш ['admin', 'kb'].
      },
      onError: (error) => {
        if (problemCode(error) !== 'kb-invalid') {
          notifyError(error);
          setPublishOpen(false);
        }
        // kb-invalid: детали показываем прямо в модальном окне (см. ниже).
      },
    });
  };

  const exportZip = async () => {
    try {
      await downloadKbExport();
    } catch (error) {
      notifyError(error);
    }
  };

  const publishError = publish.error;
  const publishBlocked = publishError && problemCode(publishError) === 'kb-invalid';

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Title order={3}>База знаний</Title>
          <Text size="sm" c="dimmed">
            Черновик правил и справочников: проверка, публикация снимков, экспорт в файлы. Клиенты
            работают на последнем опубликованном снимке.
          </Text>
        </div>
        <Group>
          <Button
            component={Link}
            to="/admin/kb/rules"
            variant="light"
            leftSection={<IconFiles size={16} />}
          >
            Правила
          </Button>
          <Button
            component={Link}
            to="/admin/kb/snapshots"
            variant="light"
            leftSection={<IconPackages size={16} />}
          >
            Снимки
          </Button>
          <Button
            component={Link}
            to="/admin/kb/reference"
            variant="light"
            leftSection={<IconTable size={16} />}
          >
            Справочники
          </Button>
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Card withBorder radius="md" padding="md">
          <Text size="xs" c="dimmed">
            Правил в черновике
          </Text>
          <Text size="xl" fw={600}>
            {status.data?.rules_total ?? '—'}
          </Text>
          <Text size="xs" c="dimmed">
            включено: {stats.enabled.data ?? '—'} · выведено: {stats.retired.data ?? '—'}
          </Text>
        </Card>
        <Card withBorder radius="md" padding="md">
          <Text size="xs" c="dimmed">
            Контрольная сумма черновика
          </Text>
          <Text size="sm" fw={600} ff="monospace" title={status.data?.checksum}>
            {status.data ? status.data.checksum.slice(0, 16) : status.isPending ? '…' : '—'}
          </Text>
          {status.data ? (
            status.data.matches_latest ? (
              <Badge color="green" variant="light" mt={4}>
                Совпадает с опубликованным
              </Badge>
            ) : (
              <Badge color="yellow" variant="light" mt={4}>
                Отличается от опубликованного
              </Badge>
            )
          ) : null}
          {status.isError ? (
            <Text size="xs" c="red" mt={4}>
              Статус не загрузился — попробуйте обновить страницу
            </Text>
          ) : null}
        </Card>
        <Card withBorder radius="md" padding="md">
          <Text size="xs" c="dimmed">
            Последняя проверка
          </Text>
          <Text size="xl" fw={600}>
            {report ? report.errors.length : '—'}
            <Text span size="sm" c="dimmed" fw={400}>
              {' '}
              ошибок · {report ? report.warnings.length : '—'} предупреждений
            </Text>
          </Text>
          {report ? (
            <Text size="xs" c="dimmed">
              Эталонные кейсы: {report.golden.passed} из{' '}
              {report.golden.passed + report.golden.failed}
            </Text>
          ) : null}
        </Card>
        <Card withBorder radius="md" padding="md">
          <Text size="xs" c="dimmed">
            Действия
          </Text>
          <Group gap="xs" mt={4}>
            <Button
              size="compact-sm"
              variant="light"
              leftSection={<IconChecklist size={14} />}
              loading={validate.isPending}
              disabled={publish.isPending}
              onClick={runValidate}
            >
              Проверить
            </Button>
            <Button
              size="compact-sm"
              color="green"
              leftSection={<IconRocket size={14} />}
              disabled={validate.isPending || publish.isPending}
              onClick={() => setPublishOpen(true)}
            >
              Опубликовать
            </Button>
          </Group>
          <Button
            size="compact-sm"
            variant="default"
            mt={6}
            leftSection={<IconDatabaseExport size={14} />}
            onClick={() => void exportZip()}
          >
            Экспорт (zip)
          </Button>
        </Card>
      </SimpleGrid>

      {report ? (
        <>
          <Divider />
          <ValidateReport report={report} />
        </>
      ) : validate.isPending ? null : (
        <Text size="sm" c="dimmed">
          Нажмите «Проверить», чтобы собрать отчёт по черновику: схема правил, слоты, циклы,
          противоречия и эталонные кейсы.
        </Text>
      )}

      <Modal
        opened={publishOpen}
        onClose={() => setPublishOpen(false)}
        title="Публикация базы знаний"
      >
        <Stack gap="sm">
          <Text size="sm">
            Перед публикацией сервер повторяет все проверки. При любой ошибке (схема, слоты, циклы,
            эталонные кейсы) снимок не создаётся, а найденное показывается ниже.
          </Text>
          <Textarea
            label="Комментарий к снимку"
            placeholder="Например: добавлены правила для платформы AM6"
            value={comment}
            onChange={(event) => setComment(event.currentTarget.value)}
            autosize
            minRows={2}
          />
          {publishBlocked ? (
            <Alert color="red" title="Публикация заблокирована">
              <Text size="sm">{publishError instanceof Error ? publishError.message : ''}</Text>
              {publishError instanceof ApiError
                ? publishError.findings.map((finding) => (
                    <Text size="sm" key={finding}>
                      • {finding}
                    </Text>
                  ))
                : null}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPublishOpen(false)}>
              Отмена
            </Button>
            <Button color="green" loading={publish.isPending} onClick={doPublish}>
              Опубликовать
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
