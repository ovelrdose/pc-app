import { Badge, Button, Group, Modal, Table, Text, Title } from '@mantine/core';
import { IconDatabaseExport, IconHistory } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { formatDateTime } from '../../lib/format';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { downloadKbExport, useRepublishSnapshot, useSnapshots } from './api';

/** Опубликованные снимки базы знаний: версии, переиздание (откат), экспорт. */
export function SnapshotsPage() {
  const snapshots = useSnapshots();
  const republish = useRepublishSnapshot();
  const [republishTarget, setRepublishTarget] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const items = snapshots.data ?? [];

  const doRepublish = () => {
    if (republishTarget === null) return;
    republish.mutate(republishTarget, {
      onSuccess: (result) => {
        notifications.show({
          color: 'green',
          title: result.created
            ? `Снимок переиздан как v${result.version}`
            : 'Переиздание не потребовалось',
          message: result.created
            ? 'Ядро перешло на содержимое выбранного снимка; черновик не изменился.'
            : 'Текущий снимок уже совпадает с выбранным.',
        });
        setRepublishTarget(null);
      },
      onError: notifyError,
    });
  };

  const exportZip = async () => {
    setExporting(true);
    try {
      await downloadKbExport();
    } catch (error) {
      notifyError(error);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={3}>Снимки базы знаний</Title>
          <Text size="sm" c="dimmed">
            Каждая публикация — неизменяемая версия правил и справочников. Ядро работает на
            последней.
          </Text>
        </div>
        <Button
          variant="light"
          leftSection={<IconDatabaseExport size={16} />}
          loading={exporting}
          onClick={() => void exportZip()}
        >
          Экспорт (zip)
        </Button>
      </Group>

      <QueryState isPending={snapshots.isPending} error={snapshots.error} />
      {!snapshots.isPending && !snapshots.error && items.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          Снимков ещё нет: опубликуйте базу знаний с панели «База знаний».
        </Text>
      ) : null}
      {items.length > 0 ? (
        <Table striped highlightOnHover verticalSpacing="sm" mt="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Версия</Table.Th>
              <Table.Th>Контрольная сумма</Table.Th>
              <Table.Th>Комментарий</Table.Th>
              <Table.Th>Правил</Table.Th>
              <Table.Th>Предупреждений</Table.Th>
              <Table.Th>Эталонов</Table.Th>
              <Table.Th>Опубликован</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((snapshot, index) => (
              <Table.Tr key={snapshot.id}>
                <Table.Td>
                  <Badge variant={index === 0 ? 'filled' : 'light'}>v{snapshot.version}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" ff="monospace">
                    {snapshot.checksum.slice(0, 12)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{snapshot.comment ?? '—'}</Text>
                </Table.Td>
                <Table.Td>{snapshot.rules}</Table.Td>
                <Table.Td>{snapshot.warnings}</Table.Td>
                <Table.Td>{snapshot.golden}</Table.Td>
                <Table.Td>
                  <Text size="sm">{formatDateTime(snapshot.published_at)}</Text>
                  {snapshot.published_by ? (
                    <Text size="xs" c="dimmed">
                      {snapshot.published_by}
                    </Text>
                  ) : null}
                </Table.Td>
                <Table.Td>
                  <Button
                    size="compact-sm"
                    variant="light"
                    leftSection={<IconHistory size={14} />}
                    onClick={() => setRepublishTarget(snapshot.id)}
                  >
                    Переиздать
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}

      <Text size="xs" c="dimmed" mt="md">
        Переиздание создаёт новую версию с содержимым выбранного снимка — это мгновенный откат.
        Черновик при этом не меняется. <Link to="/admin/kb">К панели базы знаний</Link>
      </Text>

      <Modal
        opened={republishTarget !== null}
        onClose={() => setRepublishTarget(null)}
        title="Переиздать снимок?"
      >
        <Text size="sm">
          Будет создана <b>новая версия</b> с содержимым выбранного снимка, и ядро перейдёт на неё.
          Это способ отката: несохранённые правки черновика не затрагиваются.
        </Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setRepublishTarget(null)}>
            Отмена
          </Button>
          <Button color="orange" loading={republish.isPending} onClick={doRepublish}>
            Переиздать
          </Button>
        </Group>
      </Modal>
    </>
  );
}
