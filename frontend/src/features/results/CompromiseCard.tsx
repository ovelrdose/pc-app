import { Button, Card, Group, List, Stack, Table, Text, Title } from '@mantine/core';

import type { CompromiseOut } from '../../api/types';
import { formatRub } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';

interface CompromiseCardProps {
  compromise: CompromiseOut;
  loading: boolean;
  onAccept: () => void;
}

/** Сборка в бюджете ценой уступок: что уступили, что получилось, кнопка «подобрать так». */
export function CompromiseCard({ compromise, loading, onAccept }: CompromiseCardProps) {
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>Можно собрать за ваш бюджет — с уступками</Title>
          <Text fw={600}>{formatRub(compromise.total_price_kop)}</Text>
        </Group>
        <div>
          <Text size="sm" c="dimmed" mb={4}>
            Система уступала по порядку: сначала то, что меньше всего меняет впечатление от
            компьютера, и только столько, сколько нужно для бюджета.
          </Text>
          <List type="ordered" spacing={4}>
            {compromise.concessions.map((concession) => (
              <List.Item key={concession.title}>{concession.title}</List.Item>
            ))}
          </List>
        </div>
        <Table fz="sm">
          <Table.Tbody>
            {compromise.items.map((item) => (
              <Table.Tr key={item.category}>
                <Table.Td c="dimmed">{CATEGORY_TITLES[item.category]}</Table.Td>
                <Table.Td>{item.name}</Table.Td>
                <Table.Td ta="right">{formatRub(item.price_kop)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Group justify="space-between" align="center">
          <Text size="sm" c="dimmed">
            Дальше — обычные три варианта: детали можно заменить, сборку — сохранить.
          </Text>
          <Button loading={loading} onClick={onAccept}>
            Подобрать с этими уступками
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
