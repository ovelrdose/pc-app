import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CompareOut } from '../../api/types';
import { buildDetail, consultation } from '../../../tests/fixtures';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ComparePage } from './ComparePage';

describe('ComparePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает состав, цены и FPS сборок рядом', async () => {
    const [economy, optimum] = consultation.builds;
    if (!economy || !optimum) throw new Error('нет сборок');
    const fps = buildDetail.performance.games;
    const data: CompareOut = {
      builds: [economy, optimum],
      rows: [
        { category: 'cpu', items: [economy.items[0] ?? null, optimum.items[0] ?? null] },
        { category: 'gpu', items: [economy.items[1] ?? null, optimum.items[1] ?? null] },
      ],
      games: [fps.map((e) => ({ ...e, fps: 48 })), fps],
      balance: [{ gpu_utilization: 0.9 }, { gpu_utilization: 0.97 }],
    };
    const api = mockApi([route('POST', /\/builds\/compare$/, () => data)]);
    renderWithProviders(<ComparePage />, { route: '/compare?ids=b1,b2' });

    expect(await screen.findByText('Sapphire RX 7600')).toBeInTheDocument();
    expect(screen.getByText('AMD Ryzen 7 7700')).toBeInTheDocument();
    expect(screen.getByText('≈ 48')).toBeInTheDocument();
    expect(screen.getByText('≈ 92')).toBeInTheDocument();
    expect(screen.getByText('97%')).toBeInTheDocument();
    expect(api.calls[0]?.body).toEqual({ build_ids: ['b1', 'b2'] });
  });
});
