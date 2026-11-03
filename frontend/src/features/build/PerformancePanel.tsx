import { Badge, Card, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';

import type { PerformanceOut } from '../../api/types';
import { formatFps, formatMinutes } from '../../lib/format';
import { BENCHMARK_TITLES, PRESET_TITLES } from '../../lib/labels';
import { BalanceIndicator } from './BalanceIndicator';
import { FpsChart } from './FpsChart';

interface PerformancePanelProps {
  performance: PerformanceOut;
}

/** Прогноз: FPS в играх, время задач в программах, бенчмарки, баланс. */
export function PerformancePanel({ performance }: PerformancePanelProps) {
  const { games, apps, benchmarks, balance, disclaimer } = performance;
  const resolution = games[0]?.resolution;

  return (
    <Stack gap="lg">
      {games.length > 0 && (
        <Card withBorder>
          <Title order={4}>Игры{resolution ? `, ${resolution}` : ''}</Title>
          <FpsChart games={games} />
          <Table mt="md" fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Игра</Table.Th>
                <Table.Th>Пресет</Table.Th>
                <Table.Th>FPS</Table.Th>
                <Table.Th>Диапазон</Table.Th>
                <Table.Th>Ограничивает</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {games.map((estimate) => (
                <Table.Tr key={`${estimate.game}-${estimate.preset}`}>
                  <Table.Td>{estimate.title}</Table.Td>
                  <Table.Td>{PRESET_TITLES[estimate.preset] ?? estimate.preset}</Table.Td>
                  <Table.Td>{formatFps(estimate.fps)}</Table.Td>
                  <Table.Td c="dimmed">
                    {Math.round(estimate.low)}–{Math.round(estimate.high)}
                  </Table.Td>
                  <Table.Td>
                    {estimate.limited_by === 'cpu' ? 'процессор' : 'видеокарта'}
                    {!estimate.vram_ok && (
                      <Badge ml={6} size="xs" color="orange">
                        мало видеопамяти
                      </Badge>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Card withBorder>
          <Title order={4} mb="sm">
            Баланс
          </Title>
          <BalanceIndicator balance={balance} />
        </Card>
        <Card withBorder>
          <Title order={4} mb="sm">
            Бенчмарки
          </Title>
          <Table fz="sm">
            <Table.Tbody>
              {benchmarks.map((benchmark) => (
                <Table.Tr key={benchmark.name}>
                  <Table.Td>{BENCHMARK_TITLES[benchmark.name] ?? benchmark.name}</Table.Td>
                  <Table.Td ta="right">
                    {Math.round(benchmark.value)}
                    {benchmark.estimated && (
                      <Text span size="xs" c="dimmed">
                        {' '}
                        (оценка)
                      </Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      </SimpleGrid>

      {apps.length > 0 && (
        <Card withBorder>
          <Title order={4} mb="sm">
            Программы
          </Title>
          <Table fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Программа</Table.Th>
                <Table.Th>Задача</Table.Th>
                <Table.Th>Время</Table.Th>
                <Table.Th>Эталон</Table.Th>
                <Table.Th>Уровень</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {apps.map((app) => (
                <Table.Tr key={app.app}>
                  <Table.Td>{app.title}</Table.Td>
                  <Table.Td>{app.task}</Table.Td>
                  <Table.Td>{formatMinutes(app.minutes)}</Table.Td>
                  <Table.Td c="dimmed">{formatMinutes(app.reference_minutes)}</Table.Td>
                  <Table.Td>
                    {app.pro_ok ? (
                      <Badge color="teal">профессиональный</Badge>
                    ) : app.basic_ok ? (
                      <Badge color="blue">базовый</Badge>
                    ) : (
                      <Badge color="red">не тянет</Badge>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}

      <Text size="xs" c="dimmed">
        {disclaimer}
      </Text>
    </Stack>
  );
}
