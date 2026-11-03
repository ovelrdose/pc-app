import { Button, Card, Drawer, Group, Stack, Text } from '@mantine/core';

import type { Category } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { formatRub } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';
import { useAlternatives } from './api';
import { DeltaBadges } from './DeltaBadges';

interface AlternativesDrawerProps {
  buildId: string;
  category: Category | null;
  isApplying: boolean;
  onClose: () => void;
  onReplace: (componentId: string) => void;
}

/** Совместимые замены детали: сначала укладывающиеся в бюджет. */
export function AlternativesDrawer({
  buildId,
  category,
  isApplying,
  onClose,
  onReplace,
}: AlternativesDrawerProps) {
  const alternatives = useAlternatives(buildId, category);
  return (
    <Drawer
      opened={category !== null}
      onClose={onClose}
      position="right"
      size="lg"
      title={category ? `Замены: ${CATEGORY_TITLES[category]}` : ''}
    >
      <QueryState isPending={alternatives.isPending} error={alternatives.error} />
      {alternatives.data?.length === 0 && <Text c="dimmed">Совместимых замен в каталоге нет.</Text>}
      <Stack gap="sm">
        {alternatives.data?.map((alternative) => (
          <Card withBorder key={alternative.component_id} padding="sm">
            <Stack gap={6}>
              <Group justify="space-between" wrap="nowrap">
                <Text fw={500}>{alternative.name}</Text>
                <Text>{formatRub(alternative.price_kop)}</Text>
              </Group>
              <DeltaBadges
                priceDeltaKop={alternative.price_delta_kop}
                utilityDeltaPct={alternative.utility_delta_pct}
                fpsDeltaPct={alternative.fps_delta_pct}
              />
              {alternative.verdict === 'over_budget' && (
                <Text size="xs" c="orange">
                  Выходит за бюджет
                </Text>
              )}
              {alternative.reasons.map((reason) => (
                <Text size="xs" c="dimmed" key={reason.message}>
                  {reason.message}
                </Text>
              ))}
              <Button
                size="xs"
                variant="light"
                w="fit-content"
                loading={isApplying}
                onClick={() => onReplace(alternative.component_id)}
              >
                Заменить
              </Button>
            </Stack>
          </Card>
        ))}
      </Stack>
    </Drawer>
  );
}
