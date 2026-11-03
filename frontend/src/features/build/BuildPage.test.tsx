import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BuildDetail, ExplanationOut, ModificationOut } from '../../api/types';
import { buildDetail, item } from '../../../tests/fixtures';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { BuildPage } from './BuildPage';

function renderBuild(id = 'b2') {
  return renderWithProviders(
    <Routes>
      <Route path="/builds/:id" element={<BuildPage />} />
    </Routes>,
    { route: `/builds/${id}` },
  );
}

const cheaperGpu = item('gpu', 'Sapphire RX 9070', 58000);
const edited: BuildDetail = {
  ...buildDetail,
  id: 'b4',
  parent_build_id: 'b2',
  items: [buildDetail.items[0]!, cheaperGpu],
  total_price_kop: 8_300_000,
};
const modification: ModificationOut = {
  build: edited,
  changes: [
    { category: 'gpu', before: buildDetail.items[1]!, after: cheaperGpu, delta_kop: -1_200_000 },
  ],
  price_delta_kop: -1_200_000,
  fps_avg_before: 92.4,
  fps_avg_after: 81,
};

const explanation: ExplanationOut = {
  reasoning: [
    {
      step: 1,
      rule_code: 'PRF-003',
      rule_name: 'Игровой профиль',
      explanation: 'Вы указали современные игры — главная деталь видеокарта',
      rule_cf: 0.9,
      premise_cf: 1,
      matched: [],
      effects: [{ path: 'profile.primary', outcome: 'set', value: 'aaa_gaming', cf: 0.9 }],
    },
  ],
  utility: 0.82,
  scenario_contributions: { aaa_gaming: 0.8, office: 0 },
  preferences: [],
  issues: [],
};

describe('BuildPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает состав и замечания, правка «дешевле» ведёт на новую сборку с разницей', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/builds\/b2$/, () => buildDetail),
      route('POST', /\/builds\/b2\/modifications$/, () => modification),
      route('GET', /\/builds\/b4$/, () => edited),
    ]);
    renderBuild();

    expect(await screen.findByText('Сборка «Оптимум»')).toBeInTheDocument();
    expect(screen.getByText('Запас блока питания небольшой')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute(
      'href',
      '/api/v1/builds/b2/pdf',
    );

    await user.click(screen.getByRole('button', { name: 'Действия: Sapphire RX 9070 XT' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Дешевле' }));

    // Переход на новую сборку в jsdom занимает дольше стандартной секунды ожидания.
    const title = await screen.findByText('Сборка изменена', {}, { timeout: 5000 });
    const alert = title.closest<HTMLElement>('[role="alert"]');
    if (!alert) throw new Error('нет блока с разницей');
    expect(within(alert).getByText(/Sapphire RX 9070 XT → Sapphire RX 9070/)).toBeInTheDocument();
    expect(within(alert).getByText(/средний FPS: ≈ 92 → ≈ 81/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Предыдущая версия' })).toHaveAttribute(
      'href',
      '/builds/b2',
    );
    const call = api.calls.find((c) => c.path.endsWith('/modifications'));
    expect(call?.body).toEqual({ kind: 'cheaper', category: 'gpu' });
  });

  it('перераспределяет средства из вкладки «Состав»', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/builds\/b2$/, () => buildDetail),
      route('POST', /\/builds\/b2\/modifications$/, () => modification),
      route('GET', /\/builds\/b4$/, () => edited),
    ]);
    renderBuild();

    await user.click(await screen.findByRole('button', { name: 'Перераспределить средства' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('textbox', { name: 'Сэкономить на' }));
    await user.click(await screen.findByRole('option', { name: /^Процессор/ }));
    await user.click(within(dialog).getByRole('textbox', { name: 'Вложить в' }));
    await user.click(await screen.findByRole('option', { name: /^Видеокарта/ }));
    await user.click(within(dialog).getByRole('button', { name: 'Пересобрать' }));

    await vi.waitFor(() => {
      const call = api.calls.find((c) => c.path.endsWith('/modifications'));
      expect(call?.body).toEqual({ kind: 'shift_budget', category: 'cpu', to_category: 'gpu' });
    });
  });

  it('объяснение: простой и экспертный режим', async () => {
    const user = userEvent.setup();
    mockApi([
      route('GET', /\/builds\/b2$/, () => buildDetail),
      route('GET', /\/builds\/b2\/explanation$/, () => explanation),
    ]);
    renderBuild();

    await user.click(await screen.findByRole('tab', { name: 'Почему так' }));
    expect(
      await screen.findByText('Вы указали современные игры — главная деталь видеокарта'),
    ).toBeInTheDocument();
    expect(screen.queryByText('PRF-003')).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Экспертный режим' }));
    expect(screen.getByText('PRF-003')).toBeInTheDocument();
    expect(screen.getByText('profile.primary = aaa_gaming (CF 0.90)')).toBeInTheDocument();
  });

  it('сохраняет сборку', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/builds\/b2$/, () => buildDetail),
      route('PATCH', /\/builds\/b2$/, () => ({ ...buildDetail, is_saved: true })),
    ]);
    renderBuild();

    await user.click(await screen.findByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByRole('button', { name: 'Сохранена' })).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ is_saved: true });
  });
});
