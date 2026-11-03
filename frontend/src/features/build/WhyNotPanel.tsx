import { Alert, Button, Card, List, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';

import type { ComponentOut } from '../../api/types';
import { ComponentSearch } from '../../components/ComponentSearch';
import { QueryState } from '../../components/QueryState';
import { VERDICT_TITLES } from '../../lib/labels';
import { useWhyNot } from './api';
import { DeltaBadges } from './DeltaBadges';
import { useApplyEdit } from './useApplyEdit';

const POSITIVE = new Set(['better', 'worse', 'in_build']);

interface WhyNotPanelProps {
  buildId: string;
  expert: boolean;
}

/** «Почему не этот товар?»: причины по правилам и, если можно, замена. */
export function WhyNotPanel({ buildId, expert }: WhyNotPanelProps) {
  const [selected, setSelected] = useState<ComponentOut | null>(null);
  const answer = useWhyNot(buildId, selected?.id ?? null);
  const { apply, isPending } = useApplyEdit(buildId);

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Title order={4}>Почему не этот товар?</Title>
        <ComponentSearch label="Товар из каталога" onSelect={setSelected} />
        {selected && <QueryState isPending={answer.isPending} error={answer.error} />}
        {selected && answer.data && (
          <Alert
            color={POSITIVE.has(answer.data.verdict) ? 'teal' : 'orange'}
            title={`${selected.name}: ${VERDICT_TITLES[answer.data.verdict] ?? answer.data.verdict}`}
          >
            <Stack gap="xs">
              {answer.data.reasons.length > 0 && (
                <List size="sm" spacing={4}>
                  {answer.data.reasons.map((reason) => (
                    <List.Item key={reason.message}>
                      {reason.message}
                      {expert && reason.rule_code && (
                        <Text span size="xs" c="dimmed">
                          {' '}
                          ({reason.rule_code})
                        </Text>
                      )}
                    </List.Item>
                  ))}
                </List>
              )}
              <DeltaBadges
                priceDeltaKop={answer.data.price_delta_kop}
                utilityDeltaPct={answer.data.utility_delta_pct}
                fpsDeltaPct={answer.data.fps_delta_pct}
              />
              {answer.data.can_replace && (
                <Button
                  size="xs"
                  w="fit-content"
                  loading={isPending}
                  onClick={() =>
                    apply({
                      kind: 'replace',
                      category: selected.category,
                      component_id: selected.id,
                    })
                  }
                >
                  Поставить в сборку
                </Button>
              )}
            </Stack>
          </Alert>
        )}
      </Stack>
    </Card>
  );
}
