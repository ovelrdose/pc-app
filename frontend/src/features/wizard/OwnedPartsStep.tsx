import { ActionIcon, Group, Paper, Stack, Text } from '@mantine/core';
import { IconX } from '@tabler/icons-react';

import type { Category } from '../../api/types';
import { ComponentSearch } from '../../components/ComponentSearch';
import { formatRub } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';

/** Имеющаяся деталь: из поиска по каталогу или из прошлой консультации. */
export interface OwnedPart {
  id: string;
  category: Category;
  name: string;
  price_kop: number;
}

interface OwnedPartsStepProps {
  owned: OwnedPart[];
  onChange: (owned: OwnedPart[]) => void;
}

/** Шаг «Что у вас уже есть»: эти детали останутся в сборке и не войдут в цену. */
export function OwnedPartsStep({ owned, onChange }: OwnedPartsStepProps) {
  return (
    <Stack gap="md">
      <Text c="dimmed" size="sm">
        Если какие-то детали у вас уже есть, найдите их в каталоге — система подберёт остальное с
        учётом совместимости, а их стоимость не войдёт в бюджет. Шаг можно пропустить.
      </Text>
      <ComponentSearch
        label="Найти деталь в каталоге"
        onSelect={(component) => {
          const rest = owned.filter((item) => item.category !== component.category);
          onChange([...rest, component]);
        }}
      />
      {owned.length > 0 && (
        <Stack gap="xs">
          {owned.map((item) => (
            <Paper withBorder p="xs" key={item.id}>
              <Group justify="space-between" wrap="nowrap">
                <div>
                  <Text size="xs" c="dimmed">
                    {CATEGORY_TITLES[item.category]}
                  </Text>
                  <Text size="sm">{item.name}</Text>
                </div>
                <Group gap="xs" wrap="nowrap">
                  <Text size="sm" c="dimmed">
                    {formatRub(item.price_kop)}
                  </Text>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label={`Убрать ${item.name}`}
                    onClick={() => onChange(owned.filter((other) => other.id !== item.id))}
                  >
                    <IconX size={16} />
                  </ActionIcon>
                </Group>
              </Group>
            </Paper>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
