import { Alert, List, Text } from '@mantine/core';
import { IconArrowsExchange } from '@tabler/icons-react';

import type { ModificationOut } from '../../api/types';
import { formatFps, formatRubDelta } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';

interface ChangeSummaryProps {
  modification: ModificationOut;
}

/** Что изменилось после правки: детали, цена, средний FPS. */
export function ChangeSummary({ modification }: ChangeSummaryProps) {
  const { changes, price_delta_kop, fps_avg_before, fps_avg_after } = modification;
  return (
    <Alert color="blue" icon={<IconArrowsExchange />} title="Сборка изменена">
      {changes.length === 0 ? (
        <Text size="sm">Состав не изменился: лучшего варианта с новыми условиями нет.</Text>
      ) : (
        <List size="sm" spacing={4}>
          {changes.map((change) => (
            <List.Item key={change.category}>
              {CATEGORY_TITLES[change.category]}: {change.before?.name ?? 'нет'} →{' '}
              {change.after?.name ?? 'нет'} ({formatRubDelta(change.delta_kop)})
            </List.Item>
          ))}
        </List>
      )}
      <Text size="sm" mt="xs">
        Цена: {formatRubDelta(price_delta_kop)}
        {fps_avg_before !== null &&
          fps_avg_after !== null &&
          ` · средний FPS: ${formatFps(fps_avg_before)} → ${formatFps(fps_avg_after)}`}
      </Text>
    </Alert>
  );
}
