import { Badge, HoverCard, List, Text } from '@mantine/core';

import type { ComponentStatus } from '../../api/types';
import { STATUS_COLORS, STATUS_HINTS, STATUS_TITLES } from './labels';

interface StatusBadgeProps {
  status: ComponentStatus;
  /** Причины статуса (`status_issues`) — показываем по наведению. */
  issues: string[];
}

/** Бейдж статуса компонента; причины статуса раскрываются по наведению. */
export function StatusBadge({ status, issues }: StatusBadgeProps) {
  const badge = (
    <Badge color={STATUS_COLORS[status]} variant="light">
      {STATUS_TITLES[status]}
    </Badge>
  );
  if (issues.length === 0) {
    return (
      <HoverCard width={280} shadow="md" withinPortal>
        <HoverCard.Target>{badge}</HoverCard.Target>
        <HoverCard.Dropdown>
          <Text size="sm">{STATUS_HINTS[status]}</Text>
        </HoverCard.Dropdown>
      </HoverCard>
    );
  }
  return (
    <HoverCard width={320} shadow="md" withinPortal>
      <HoverCard.Target>{badge}</HoverCard.Target>
      <HoverCard.Dropdown>
        <Text size="sm" fw={500}>
          {STATUS_TITLES[status]}
        </Text>
        <Text size="sm" c="dimmed">
          {STATUS_HINTS[status]}
        </Text>
        <List size="sm" mt="xs" spacing={4}>
          {issues.map((issue) => (
            <List.Item key={issue}>{issue}</List.Item>
          ))}
        </List>
      </HoverCard.Dropdown>
    </HoverCard>
  );
}
