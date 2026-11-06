import { Anchor, Badge, HoverCard, Table, Text } from '@mantine/core';
import { Link } from 'react-router-dom';

import type { RuleOut } from '../../api/types';
import { RULE_KIND_COLORS, RULE_KIND_TITLES } from './labels';

interface RulesTableProps {
  items: RuleOut[];
  /** Переход в редактор (для сгенерированных — с подтверждением override). */
  onEdit: (rule: RuleOut) => void;
}

/** Таблица правил: код-ссылка, название, группа, бейджи вида/происхождения/статуса. */
export function RulesTable({ items, onEdit }: RulesTableProps) {
  return (
    <Table striped highlightOnHover verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Код</Table.Th>
          <Table.Th>Название</Table.Th>
          <Table.Th>Группа</Table.Th>
          <Table.Th>Вид</Table.Th>
          <Table.Th>Происхождение</Table.Th>
          <Table.Th>Статус</Table.Th>
          <Table.Th>Приоритет</Table.Th>
          <Table.Th>CF</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((rule) => (
          <Table.Tr key={rule.code}>
            <Table.Td>
              <Anchor
                component={Link}
                to={`/admin/kb/rules/${rule.code}`}
                fw={500}
                onClick={(event) => {
                  event.preventDefault();
                  onEdit(rule);
                }}
              >
                {rule.code}
              </Anchor>
            </Table.Td>
            <Table.Td>
              <Text size="sm">{rule.name}</Text>
              {rule.source ? (
                <Text size="xs" c="dimmed">
                  {rule.source}
                </Text>
              ) : null}
            </Table.Td>
            <Table.Td>{rule.group}</Table.Td>
            <Table.Td>
              <Badge color={RULE_KIND_COLORS[rule.kind]} variant="light">
                {RULE_KIND_TITLES[rule.kind]}
              </Badge>
            </Table.Td>
            <Table.Td>
              {rule.origin === 'generated' ? (
                <HoverCard width={300} shadow="md" withinPortal>
                  <HoverCard.Target>
                    <Badge color="teal" variant="light" style={{ cursor: 'help' }}>
                      Сгенерировано
                    </Badge>
                  </HoverCard.Target>
                  <HoverCard.Dropdown>
                    <Text size="sm">
                      Правило построено генератором из справочников. Правятся справочники
                      («Справочники → Перегенерировать»); ручная правка переведёт правило в «ручные»
                      (override) и генератор его больше не перезапишет.
                    </Text>
                  </HoverCard.Dropdown>
                </HoverCard>
              ) : (
                <Badge color="gray" variant="light">
                  Ручное
                </Badge>
              )}
            </Table.Td>
            <Table.Td>
              {rule.enabled ? (
                <Badge color="green" variant="light">
                  Включено
                </Badge>
              ) : (
                <Badge color="gray" variant="light">
                  Выведено
                </Badge>
              )}
            </Table.Td>
            <Table.Td>{rule.priority}</Table.Td>
            <Table.Td>{rule.cf}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
