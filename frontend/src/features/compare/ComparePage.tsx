import { Anchor, Card, SegmentedControl, Stack, Table, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import type { CompareOut } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { formatFps, formatRub, formatShare } from '../../lib/format';
import { CATEGORY_TITLES, PRESET_TITLES, TIER_TITLES } from '../../lib/labels';
import { useCompare } from './api';

const MAX_BUILDS = 3;

/** Строки FPS: игра → FPS каждой сборки на выбранном пресете. */
function fpsRows(data: CompareOut, preset: string) {
  const titles = new Map<string, string>();
  for (const games of data.games) {
    for (const estimate of games) titles.set(estimate.game, estimate.title);
  }
  return [...titles].map(([game, title]) => ({
    game,
    title,
    values: data.games.map(
      (games) => games.find((e) => e.game === game && e.preset === preset)?.fps ?? null,
    ),
  }));
}

/** Сравнение сборок: состав, цена, FPS, баланс. */
export function ComparePage() {
  const [params] = useSearchParams();
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean).slice(0, MAX_BUILDS);
  const compare = useCompare(ids);
  const [preset, setPreset] = useState('high');

  if (ids.length < 2) {
    return <Text py="xl">Для сравнения нужно выбрать две или три сборки.</Text>;
  }
  if (!compare.data) return <QueryState isPending={compare.isPending} error={compare.error} />;
  const data = compare.data;
  const presets = [...new Set(data.games.flat().map((e) => e.preset))];

  return (
    <Stack gap="lg" py="md">
      <Title order={2}>Сравнение сборок</Title>
      <Card withBorder>
        <Table.ScrollContainer minWidth={640}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                {data.builds.map((build) => (
                  <Table.Th key={build.id}>
                    <Anchor component={Link} to={`/builds/${build.id}`}>
                      {build.title ?? TIER_TITLES[build.tier]}
                    </Anchor>
                  </Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td fw={600}>Цена</Table.Td>
                {data.builds.map((build) => (
                  <Table.Td key={build.id} fw={600}>
                    {formatRub(build.total_price_kop)}
                  </Table.Td>
                ))}
              </Table.Tr>
              {data.rows.map((row) => {
                const names = row.items.map((item) => item?.sku ?? '');
                const differs = new Set(names).size > 1;
                return (
                  <Table.Tr key={row.category}>
                    <Table.Td c="dimmed">{CATEGORY_TITLES[row.category]}</Table.Td>
                    {row.items.map((item, index) => (
                      <Table.Td
                        key={data.builds[index]?.id ?? index}
                        fw={differs ? 500 : undefined}
                      >
                        {item ? item.name : '—'}
                      </Table.Td>
                    ))}
                  </Table.Tr>
                );
              })}
              <Table.Tr>
                <Table.Td c="dimmed">Загрузка видеокарты</Table.Td>
                {data.balance.map((balance, index) => (
                  <Table.Td key={data.builds[index]?.id ?? index}>
                    {typeof balance.gpu_utilization === 'number'
                      ? formatShare(balance.gpu_utilization)
                      : '—'}
                  </Table.Td>
                ))}
              </Table.Tr>
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      {presets.length > 0 && (
        <Card withBorder>
          <Stack gap="sm">
            <Title order={4}>FPS в ваших играх</Title>
            <SegmentedControl
              w="fit-content"
              value={preset}
              onChange={setPreset}
              data={presets.map((value) => ({ value, label: PRESET_TITLES[value] ?? value }))}
            />
            <Table>
              <Table.Tbody>
                {fpsRows(data, preset).map((row) => (
                  <Table.Tr key={row.game}>
                    <Table.Td>{row.title}</Table.Td>
                    {row.values.map((fps, index) => (
                      <Table.Td key={data.builds[index]?.id ?? index}>
                        {fps === null ? '—' : formatFps(fps)}
                      </Table.Td>
                    ))}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
