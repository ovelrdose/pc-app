import type { BuildSummary, Tier } from '../../api/types';

/** Варианты с одинаковым составом показываются одной карточкой. */
export interface BuildGroup {
  build: BuildSummary;
  tiers: Tier[];
}

/**
 * Исходные варианты подбора, объединённые по одинаковому набору товаров (порядок сохраняется).
 * Сборки после правок (с родителем) сюда не входят.
 */
export function groupBuilds(builds: BuildSummary[]): BuildGroup[] {
  const groups = new Map<string, BuildGroup>();
  for (const build of builds.filter((b) => b.parent_build_id === null)) {
    const key = build.items
      .map((item) => item.sku)
      .sort()
      .join('|');
    const group = groups.get(key);
    if (group) group.tiers.push(build.tier);
    else groups.set(key, { build, tiers: [build.tier] });
  }
  return [...groups.values()];
}
