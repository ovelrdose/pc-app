import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { consultation, questionnaire } from '../../../tests/fixtures';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { WizardPage } from './WizardPage';

function renderWizard(path = '/wizard') {
  return renderWithProviders(
    <Routes>
      <Route path="/wizard" element={<WizardPage />} />
      <Route path="/consultations/:id" element={<p>страница результатов</p>} />
    </Routes>,
    { route: path },
  );
}

describe('WizardPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('проходит шаги, проверяет ответы и запускает подбор', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/questionnaire$/, () => questionnaire),
      route('POST', /\/consultations$/, () => ({ ...consultation, status: 'created', builds: [] })),
      route('POST', /\/consultations\/c1\/builds$/, () => consultation),
    ]);
    renderWizard();

    expect(await screen.findByText('Для чего в основном нужен компьютер?')).toBeInTheDocument();
    expect(screen.queryByText('Чем ещё будете заниматься иногда?')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Далее' }));
    expect(screen.getByText('Выберите основную задачу')).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Современные игры' }));
    await user.click(screen.getByRole('checkbox', { name: 'Офис' }));
    // смена основной задачи убирает её из дополнительных
    await user.click(screen.getByRole('radio', { name: 'Офис' }));
    expect(screen.queryByRole('checkbox', { name: 'Офис' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Современные игры' }));
    await user.click(screen.getByRole('button', { name: 'Далее' }));

    expect(await screen.findByLabelText('Сколько готовы потратить, ₽?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Далее' }));

    await user.click(await screen.findByText('2K'));
    await user.click(screen.getByText('Скорее да'));
    await user.click(screen.getByRole('button', { name: 'Далее' }));
    await user.click(await screen.findByRole('button', { name: 'Подобрать сборки' }));

    expect(await screen.findByText('страница результатов')).toBeInTheDocument();
    const created = api.calls.find((c) => c.method === 'POST' && c.path.endsWith('/consultations'));
    expect(created?.body).toEqual({
      answers: {
        tasks: { main: 'office', extra: ['aaa_gaming'] },
        budget: 100000,
        resolution: '1440p',
        wifi: 'rather_yes',
      },
      owned_component_ids: [],
    });
  });

  it('подставляет ответы прошлой консультации', async () => {
    const user = userEvent.setup();
    mockApi([
      route('GET', /\/questionnaire$/, () => questionnaire),
      route('GET', /\/consultations\/c1$/, () => consultation),
    ]);
    renderWizard('/wizard?from=c1');

    expect(await screen.findByRole('radio', { name: 'Современные игры' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Далее' }));
    expect(await screen.findByLabelText('Сколько готовы потратить, ₽?')).toHaveValue('120 000');
  });
});
