import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { RulesPage } from './RulesPage';
import { ruleOut } from './testing/fixtures';

const rulesPage = {
  items: [
    ruleOut({ code: 'BUD-014' }),
    ruleOut({
      code: 'GEN-GAME-CP2077-ULTRA',
      kind: 'goal',
      group: 'gen_game',
      origin: 'generated',
      source: 'tables/games.yaml#cyberpunk_2077',
      enabled: false,
    }),
  ],
  total: 2,
  limit: 25,
  offset: 0,
};

function renderRules() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/kb/rules" element={<RulesPage />} />
      <Route path="/admin/kb/rules/:code" element={<div>РЕДАКТОР</div>} />
    </Routes>,
    { route: '/admin/kb/rules' },
  );
}

describe('RulesPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает бейджи вида, происхождения и статуса', async () => {
    mockApi([route('GET', /\/api\/v1\/admin\/rules$/, () => rulesPage)]);
    renderRules();

    expect(await screen.findByText('BUD-014')).toBeInTheDocument();
    const table = screen.getByRole('table');
    expect(within(table).getByText('Вывод')).toBeInTheDocument();
    expect(within(table).getByText('Сгенерировано')).toBeInTheDocument();
    expect(within(table).getByText('Ручное')).toBeInTheDocument();
    expect(within(table).getAllByText('Включено')).toHaveLength(1);
    expect(within(table).getByText('Выведено')).toBeInTheDocument();
    expect(within(table).getByText(/tables\/games.yaml#cyberpunk_2077/)).toBeInTheDocument();
  });

  it('ручное правило открывается сразу, сгенерированное — через диалог override', async () => {
    const user = userEvent.setup();
    mockApi([route('GET', /\/api\/v1\/admin\/rules$/, () => rulesPage)]);
    renderRules();

    await user.click(await screen.findByText('BUD-014'));
    expect(await screen.findByText('РЕДАКТОР')).toBeInTheDocument();
  });

  it('предупреждает об override для сгенерированного правила', async () => {
    const user = userEvent.setup();
    mockApi([route('GET', /\/api\/v1\/admin\/rules$/, () => rulesPage)]);
    renderRules();

    await user.click(await screen.findByText('GEN-GAME-CP2077-ULTRA'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/переведёт его в «ручные» \(override\)/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: /Продолжить правку/ }));
    expect(await screen.findByText('РЕДАКТОР')).toBeInTheDocument();
  });
});
