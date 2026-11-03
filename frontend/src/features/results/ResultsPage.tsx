import { Alert, Button, Group, List, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconAdjustments, IconArrowsLeftRight, IconScale } from '@tabler/icons-react';
import { Link, useParams } from 'react-router-dom';

import { QueryState } from '../../components/QueryState';
import { formatDateTime } from '../../lib/format';
import { useConsultation } from './api';
import { BuildCard } from './BuildCard';
import { EditedBuilds } from './EditedBuilds';
import { InfeasiblePanel } from './InfeasiblePanel';
import { groupBuilds } from './tiers';

/** Результаты консультации: три варианта или разбор, почему подобрать не удалось. */
export function ResultsPage() {
  const { id } = useParams();
  const consultation = useConsultation(id);

  if (!consultation.data) {
    return <QueryState isPending={consultation.isPending} error={consultation.error} />;
  }
  const data = consultation.data;
  const groups = groupBuilds(data.builds);
  const compareIds = groups.map((group) => group.build.id).join(',');
  const edited = data.builds.filter((build) => build.parent_build_id !== null);

  return (
    <Stack gap="lg" py="md">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Результаты подбора</Title>
          <Text size="sm" c="dimmed">
            {formatDateTime(data.created_at)} · база знаний {data.kb_version ?? '—'}
          </Text>
        </div>
        <Group gap="sm">
          <Button
            component={Link}
            to={`/wizard?from=${data.id}`}
            variant="default"
            leftSection={<IconAdjustments size={16} />}
          >
            Изменить ответы
          </Button>
          {groups.length > 1 && (
            <Button
              component={Link}
              to={`/compare?ids=${compareIds}`}
              variant="default"
              leftSection={<IconArrowsLeftRight size={16} />}
            >
              Сравнить варианты
            </Button>
          )}
        </Group>
      </Group>

      {data.waived.length > 0 && (
        <Alert color="yellow" icon={<IconScale />} title="Подобрано с уступками ради бюджета">
          <List size="sm" spacing={2}>
            {data.waived.map((item) => (
              <List.Item key={item.fact}>{item.title}</List.Item>
            ))}
          </List>
        </Alert>
      )}

      {data.status === 'infeasible' && <InfeasiblePanel consultation={data} />}
      {data.status === 'completed' && (
        <SimpleGrid cols={{ base: 1, md: groups.length }}>
          {groups.map((group) => (
            <BuildCard key={group.build.id} build={group.build} tiers={group.tiers} />
          ))}
        </SimpleGrid>
      )}
      {edited.length > 0 && <EditedBuilds builds={edited} />}
      {data.status === 'created' && (
        <Text c="dimmed">Подбор по этой консультации ещё не запускался.</Text>
      )}
    </Stack>
  );
}
