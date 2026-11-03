import { Group, Progress, Stack, Text } from '@mantine/core';

import { formatFps, formatShare } from '../../lib/format';

interface BalanceIndicatorProps {
  balance: Record<string, string | number | boolean | null>;
}

/** Баланс процессора и видеокарты в играх клиента. */
export function BalanceIndicator({ balance }: BalanceIndicatorProps) {
  const utilization = typeof balance.gpu_utilization === 'number' ? balance.gpu_utilization : null;
  const fpsAvg = typeof balance.fps_avg === 'number' ? balance.fps_avg : null;
  if (utilization === null) {
    return (
      <Text size="sm" c="dimmed">
        Баланс не оценивается: в сборке нет графики для игр.
      </Text>
    );
  }
  const limiter = balance.limited_by === 'cpu' ? 'процессор' : 'видеокарта';
  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Text size="sm">Загрузка видеокарты в ваших играх</Text>
        <Text size="sm" fw={600}>
          {formatShare(utilization)}
        </Text>
      </Group>
      <Progress
        value={Math.min(utilization, 1) * 100}
        color={limiter === 'процессор' ? 'orange' : 'teal'}
      />
      <Text size="sm" c="dimmed">
        FPS ограничивает {limiter}
        {fpsAvg !== null && ` · в среднем ${formatFps(fpsAvg)} кадров/с`}
      </Text>
    </Stack>
  );
}
