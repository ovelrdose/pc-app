import { Badge, Group } from '@mantine/core';

import { formatPercent, formatRubDelta } from '../../lib/format';

interface DeltaBadgesProps {
  priceDeltaKop: number | null;
  utilityDeltaPct: number | null;
  fpsDeltaPct: number | null;
}

/** Разница с текущей сборкой: цена, полезность, FPS. */
export function DeltaBadges({ priceDeltaKop, utilityDeltaPct, fpsDeltaPct }: DeltaBadgesProps) {
  return (
    <Group gap={6}>
      {priceDeltaKop !== null && (
        <Badge variant="light" color={priceDeltaKop > 0 ? 'orange' : 'teal'}>
          {formatRubDelta(priceDeltaKop)}
        </Badge>
      )}
      {utilityDeltaPct !== null && (
        <Badge variant="light" color={utilityDeltaPct >= 0 ? 'teal' : 'gray'}>
          полезность {formatPercent(utilityDeltaPct)}
        </Badge>
      )}
      {fpsDeltaPct !== null && fpsDeltaPct !== 0 && (
        <Badge variant="light" color={fpsDeltaPct > 0 ? 'teal' : 'gray'}>
          FPS {formatPercent(fpsDeltaPct)}
        </Badge>
      )}
    </Group>
  );
}
