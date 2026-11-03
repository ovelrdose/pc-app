import { Anchor, Card, Table, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';

import type { BuildSummary } from '../../api/types';
import { formatDateTime, formatRub } from '../../lib/format';
import { TIER_TITLES } from '../../lib/labels';

interface EditedBuildsProps {
  builds: BuildSummary[];
}

/** Сборки, полученные правками исходных вариантов. */
export function EditedBuilds({ builds }: EditedBuildsProps) {
  return (
    <Card withBorder>
      <Title order={4} mb="xs">
        Версии после ваших правок
      </Title>
      <Table>
        <Table.Tbody>
          {builds.map((build) => (
            <Table.Tr key={build.id}>
              <Table.Td>
                <Anchor component={Link} to={`/builds/${build.id}`}>
                  {build.title ?? `${TIER_TITLES[build.tier]}, правка`}
                </Anchor>
              </Table.Td>
              <Table.Td>{formatRub(build.total_price_kop)}</Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed">
                  {formatDateTime(build.created_at)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  );
}
