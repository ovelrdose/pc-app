import { Badge, Group, Table, Text, Tooltip } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { useState } from 'react';

import type { BuildItemOut, Category } from '../../api/types';
import { formatRub } from '../../lib/format';
import { CATEGORY_ORDER, CATEGORY_TITLES } from '../../lib/labels';
import { AlternativesDrawer } from './AlternativesDrawer';
import { ComponentActions } from './ComponentActions';
import { useApplyEdit } from './useApplyEdit';

interface ComponentListProps {
  buildId: string;
  items: BuildItemOut[];
}

/** Состав сборки с меню правок по каждой детали. */
export function ComponentList({ buildId, items }: ComponentListProps) {
  const { apply, isPending } = useApplyEdit(buildId);
  const [alternativesFor, setAlternativesFor] = useState<Category | null>(null);
  const sorted = [...items].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category),
  );

  return (
    <>
      <Table verticalSpacing="sm" highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Категория</Table.Th>
            <Table.Th>Товар</Table.Th>
            <Table.Th ta="right">Цена</Table.Th>
            <Table.Th w={40} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sorted.map((item) => (
            <Table.Tr key={item.category}>
              <Table.Td c="dimmed">{CATEGORY_TITLES[item.category]}</Table.Td>
              <Table.Td>
                <Group gap={6}>
                  <Text size="sm">{item.name}</Text>
                  {item.locked && !item.owned && (
                    <Tooltip label="Закреплена: правки её не меняют">
                      <IconLock size={14} aria-label="закреплена" />
                    </Tooltip>
                  )}
                  {item.owned && (
                    <Badge size="xs" variant="outline" color="gray">
                      уже есть у вас
                    </Badge>
                  )}
                </Group>
              </Table.Td>
              <Table.Td ta="right">{item.owned ? '—' : formatRub(item.price_kop)}</Table.Td>
              <Table.Td>
                {!item.owned && (
                  <ComponentActions
                    item={item}
                    disabled={isPending}
                    onEdit={(request) => apply(request)}
                    onAlternatives={() => setAlternativesFor(item.category)}
                  />
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <AlternativesDrawer
        buildId={buildId}
        category={alternativesFor}
        onClose={() => setAlternativesFor(null)}
        onReplace={(componentId) =>
          alternativesFor &&
          apply({ kind: 'replace', category: alternativesFor, component_id: componentId }, () =>
            setAlternativesFor(null),
          )
        }
        isApplying={isPending}
      />
    </>
  );
}
