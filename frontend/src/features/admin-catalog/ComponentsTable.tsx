import { Anchor, Menu, Switch, Table, Text } from '@mantine/core';
import { IconDotsVertical, IconPencil, IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react';
import { Link } from 'react-router-dom';

import type { ComponentOut, ComponentStatus } from '../../api/types';
import { CATEGORY_TITLES } from '../../lib/labels';
import { formatRub } from '../../lib/format';
import { StatusBadge } from './StatusBadge';
import { SOURCE_TITLES } from './labels';

interface ComponentsTableProps {
  items: ComponentOut[];
  /** Служебные правки из списка: наличие и статус продажи. */
  onToggleStock: (component: ComponentOut, inStock: boolean) => void;
  onChangeStatus: (component: ComponentOut, status: ComponentStatus) => void;
  busy: boolean;
}

/** Таблица компонентов админки: бейджи статусов с причинами, переключатель наличия, действия. */
export function ComponentsTable({
  items,
  onToggleStock,
  onChangeStatus,
  busy,
}: ComponentsTableProps) {
  return (
    <Table striped highlightOnHover verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Название</Table.Th>
          <Table.Th>Категория</Table.Th>
          <Table.Th>Бренд</Table.Th>
          <Table.Th>Цена</Table.Th>
          <Table.Th>Статус</Table.Th>
          <Table.Th>В наличии</Table.Th>
          <Table.Th>Источник</Table.Th>
          <Table.Th />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((component) => (
          <Table.Tr key={component.id}>
            <Table.Td>
              <Anchor component={Link} to={`/admin/catalog/${component.id}`} fw={500}>
                {component.name}
              </Anchor>
              <Text size="xs" c="dimmed">
                {component.sku}
              </Text>
            </Table.Td>
            <Table.Td>{CATEGORY_TITLES[component.category]}</Table.Td>
            <Table.Td>{component.brand}</Table.Td>
            <Table.Td>{formatRub(component.price_kop)}</Table.Td>
            <Table.Td>
              <StatusBadge status={component.status} issues={component.status_issues} />
            </Table.Td>
            <Table.Td>
              <Switch
                aria-label={`В наличии: ${component.name}`}
                checked={component.in_stock}
                disabled={busy || component.status === 'inactive'}
                onChange={(event) => onToggleStock(component, event.currentTarget.checked)}
              />
            </Table.Td>
            <Table.Td>{SOURCE_TITLES[component.source]}</Table.Td>
            <Table.Td>
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <IconDotsVertical size={18} aria-label={`Действия: ${component.name}`} />
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item
                    component={Link}
                    to={`/admin/catalog/${component.id}`}
                    leftSection={<IconPencil size={16} />}
                  >
                    Редактировать
                  </Menu.Item>
                  {component.status === 'inactive' ? (
                    <Menu.Item
                      leftSection={<IconPlayerPlay size={16} />}
                      onClick={() => onChangeStatus(component, 'active')}
                    >
                      Вернуть к продаже
                    </Menu.Item>
                  ) : (
                    <Menu.Item
                      color="red"
                      leftSection={<IconPlayerStop size={16} />}
                      onClick={() => onChangeStatus(component, 'inactive')}
                    >
                      Снять с продажи
                    </Menu.Item>
                  )}
                </Menu.Dropdown>
              </Menu>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
