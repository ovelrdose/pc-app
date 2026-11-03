import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { GoalOut, HypothesisOut, HypothesisRequest } from '../../api/types';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { HypothesisPanel } from './HypothesisPanel';

const goals: GoalOut[] = [
  {
    predicate: 'runs_game',
    args: { game: 'cyberpunk_2077', preset: 'ultra' },
    title: 'Потянет Cyberpunk 2077 на ультра',
    needs: ['target_fps'],
  },
];

const asks: HypothesisOut = {
  status: 'unknown',
  tree: {
    kind: 'goal',
    label: 'Cyberpunk 2077 на ультра',
    status: 'unknown',
    cf: 0,
    rule_code: null,
    detail: null,
    value: null,
    children: [],
  },
  questions: [
    { variable: 'target_fps', question: 'Какой FPS для вас комфортен?', options: [30, 60] },
  ],
};

const proved: HypothesisOut = {
  status: 'proved',
  questions: [],
  tree: {
    kind: 'goal',
    label: 'Cyberpunk 2077 на ультра',
    status: 'proved',
    cf: 1,
    rule_code: null,
    detail: null,
    value: null,
    children: [
      {
        kind: 'rule',
        label: 'FPS не ниже целевого',
        status: 'proved',
        cf: 1,
        rule_code: 'GOL-010',
        detail: '72 ≥ 60',
        value: null,
        children: [],
      },
    ],
  },
};

describe('HypothesisPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('задаёт уточняющий вопрос и показывает дерево доказательства', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/goals$/, () => goals),
      route('POST', /\/builds\/b2\/hypotheses$/, async (request) => {
        const body = (await request.json()) as HypothesisRequest;
        return body.bindings?.target_fps === undefined ? asks : proved;
      }),
    ]);
    renderWithProviders(<HypothesisPanel buildId="b2" expert />);

    await user.click(await screen.findByRole('textbox', { name: 'Что проверить' }));
    await user.click(
      await screen.findByRole('option', { name: 'Потянет Cyberpunk 2077 на ультра' }),
    );
    await user.click(screen.getByRole('button', { name: 'Проверить' }));

    expect(await screen.findByText('Нужно уточнить')).toBeInTheDocument();
    await user.click(screen.getByRole('textbox', { name: 'Какой FPS для вас комфортен?' }));
    await user.click(await screen.findByRole('option', { name: '60' }));
    await user.click(screen.getByRole('button', { name: 'Ответить и проверить' }));

    expect(await screen.findByText('Да, потянет')).toBeInTheDocument();
    expect(screen.getByText('FPS не ниже целевого')).toBeInTheDocument();
    expect(screen.getByText('rule · GOL-010 · CF 1.00')).toBeInTheDocument();
    expect(api.calls.at(-1)?.body).toEqual({
      predicate: 'runs_game',
      args: { game: 'cyberpunk_2077', preset: 'ultra' },
      bindings: { target_fps: 60 },
    });
  });
});
