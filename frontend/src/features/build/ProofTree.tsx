import { Group, Stack, Text } from '@mantine/core';
import { IconCircleCheck, IconCircleX, IconHelpCircle } from '@tabler/icons-react';

import type { ProofNodeOut } from '../../api/types';
import classes from './ProofTree.module.css';

const STATUS = {
  proved: { icon: IconCircleCheck, color: 'teal', label: 'доказано' },
  failed: { icon: IconCircleX, color: 'red', label: 'не выполнено' },
  unknown: { icon: IconHelpCircle, color: 'gray', label: 'не хватает данных' },
} as const;

interface ProofTreeProps {
  node: ProofNodeOut;
  expert: boolean;
}

function formatValue(value: ProofNodeOut['value']): string | null {
  if (value === null) return null;
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'boolean') return value ? 'да' : 'нет';
  return String(value);
}

/** Дерево доказательства гипотезы: цель → правила → условия → факты. */
export function ProofTree({ node, expert }: ProofTreeProps) {
  const status = STATUS[node.status];
  const Icon = status.icon;
  const value = formatValue(node.value);
  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap" align="flex-start">
        <Icon
          size={18}
          color={`var(--mantine-color-${status.color}-6)`}
          aria-label={status.label}
        />
        <div>
          <Text size="sm">
            {node.label}
            {value !== null && node.kind === 'fact' && (
              <Text span c="dimmed">
                {' '}
                = {value}
              </Text>
            )}
          </Text>
          {node.detail && (
            <Text size="xs" c="dimmed">
              {node.detail}
            </Text>
          )}
          {expert && (
            <Text size="xs" c="dimmed">
              {node.kind}
              {node.rule_code && ` · ${node.rule_code}`}
              {node.status === 'proved' && ` · CF ${node.cf.toFixed(2)}`}
            </Text>
          )}
        </div>
      </Group>
      {node.children.length > 0 && (
        <Stack gap={4} className={classes.children}>
          {node.children.map((child, index) => (
            <ProofTree key={`${child.label}-${index}`} node={child} expert={expert} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
