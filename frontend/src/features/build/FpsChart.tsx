import { BarChart } from '@mantine/charts';

import type { FpsOut } from '../../api/types';
import { PRESET_TITLES } from '../../lib/labels';

const PRESET_COLORS: Record<string, string> = {
  medium: 'teal.5',
  high: 'blue.6',
  ultra: 'violet.6',
};

interface FpsChartProps {
  games: FpsOut[];
}

/** Столбчатая диаграмма FPS: игры × пресеты графики. */
export function FpsChart({ games }: FpsChartProps) {
  const presets = [...new Set(games.map((g) => g.preset))];
  const rows = new Map<string, Record<string, string | number>>();
  for (const estimate of games) {
    const row = rows.get(estimate.game) ?? { game: estimate.title };
    row[estimate.preset] = Math.round(estimate.fps);
    rows.set(estimate.game, row);
  }
  return (
    <BarChart
      h={Math.max(220, rows.size * 70)}
      data={[...rows.values()]}
      dataKey="game"
      orientation="vertical"
      yAxisProps={{ width: 140 }}
      series={presets.map((preset) => ({
        name: preset,
        label: PRESET_TITLES[preset] ?? preset,
        color: PRESET_COLORS[preset] ?? 'gray.6',
      }))}
      withLegend
      unit=" FPS"
    />
  );
}
