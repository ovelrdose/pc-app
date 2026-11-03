import { Badge, Button, Card, Group, Stack, Table, Text } from '@mantine/core';
import { Link } from 'react-router-dom';

import type { BuildSummary, Tier } from '../../api/types';
import { formatRub } from '../../lib/format';
import { CATEGORY_ORDER, CATEGORY_TITLES, TIER_DESCRIPTIONS, TIER_TITLES } from '../../lib/labels';

interface BuildCardProps {
  build: BuildSummary;
  tiers: Tier[];
}

/** Карточка варианта сборки: цена и состав. */
export function BuildCard({ build, tiers }: BuildCardProps) {
  const items = [...build.items].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category),
  );
  const ownedTotal = build.items.some((item) => item.owned);

  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="sm" h="100%">
        <Group gap="xs">
          {tiers.map((tier) => (
            <Badge key={tier} size="lg" variant={tier === 'optimum' ? 'filled' : 'light'}>
              {TIER_TITLES[tier]}
            </Badge>
          ))}
        </Group>
        <Text size="sm" c="dimmed">
          {tiers.length > 1
            ? 'Эти варианты совпали: лучшего состава в бюджете нет'
            : TIER_DESCRIPTIONS[build.tier]}
        </Text>
        <Text fz={28} fw={700}>
          {formatRub(build.total_price_kop)}
        </Text>
        {ownedTotal && (
          <Text size="xs" c="dimmed">
            без учёта имеющихся у вас деталей
          </Text>
        )}
        <Table verticalSpacing={4} fz="sm">
          <Table.Tbody>
            {items.map((item) => (
              <Table.Tr key={item.category}>
                <Table.Td c="dimmed" w="38%">
                  {CATEGORY_TITLES[item.category]}
                </Table.Td>
                <Table.Td>
                  {item.name}
                  {item.owned && (
                    <Badge ml={6} size="xs" variant="outline" color="gray">
                      ваша
                    </Badge>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Button component={Link} to={`/builds/${build.id}`} mt="auto" variant="light">
          Подробнее о сборке
        </Button>
      </Stack>
    </Card>
  );
}
