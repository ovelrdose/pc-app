import { describe, expect, it } from 'vitest';

import { consultation } from '../../../tests/fixtures';
import { groupBuilds } from './tiers';

describe('groupBuilds', () => {
  it('объединяет варианты с одинаковым составом и пропускает правки', () => {
    const edited = { ...consultation.builds[0]!, id: 'b9', parent_build_id: 'b1' };
    const groups = groupBuilds([...consultation.builds, edited]);
    expect(groups.map((g) => [g.build.id, g.tiers])).toEqual([
      ['b1', ['economy']],
      ['b2', ['optimum', 'maximum']],
    ]);
  });
});
