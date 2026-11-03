import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { InfeasibleOut } from '../../api/types';
import { consultation } from '../../../tests/fixtures';
import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ResultsPage } from './ResultsPage';

function renderResults(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/consultations/:id" element={<ResultsPage />} />
    </Routes>,
    { route: `/consultations/${id}` },
  );
}

const report: InfeasibleOut = {
  budget_rub: 40000,
  min_budget_rub: 61500,
  blocking: [
    {
      fact: 'req.gpu_min_tier',
      title: 'Минимальный класс видеокарты',
      value: 3,
      rules: ['REQ-012'],
      min_budget_without_rub: 38000,
    },
  ],
  relaxations: [
    {
      title: 'Разрешение 1080p вместо 1440p',
      answers: { resolution: '1080p' },
      min_budget_rub: 45200,
    },
  ],
  compromise: {
    concessions: [
      { title: 'SSD 500 ГБ вместо 1000', answers: { storage_gb: 500 }, waived: [] },
      {
        title: 'Процессор слабее рекомендованного',
        answers: {},
        waived: ['req.cpu_single_min'],
      },
    ],
    answers: { storage_gb: 500 },
    waived: ['req.cpu_single_min'],
    total_price_kop: 3_950_000,
    items: [],
  },
  best_effort: null,
};

describe('ResultsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает варианты и объединяет одинаковые', async () => {
    mockApi([route('GET', /\/consultations\/c1$/, () => consultation)]);
    renderResults('c1');

    expect(await screen.findByText('Результаты подбора')).toBeInTheDocument();
    expect(screen.getByText('Эконом')).toBeInTheDocument();
    expect(screen.getByText('Оптимум')).toBeInTheDocument();
    expect(screen.getByText('Максимум')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Подробнее о сборке' })).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Сравнить варианты' })).toHaveAttribute(
      'href',
      '/compare?ids=b1,b2',
    );
  });

  it('разбирает невыполнимый запрос и подбирает с ослаблением', async () => {
    const user = userEvent.setup();
    const infeasible = {
      ...consultation,
      id: 'c2',
      status: 'infeasible' as const,
      answers: { tasks: { main: 'aaa_gaming' }, budget: 40000, resolution: '1440p' },
      builds: [],
      infeasibility: null,
    };
    const api = mockApi([
      route('GET', /\/consultations\/c2$/, () => infeasible),
      route('GET', /\/consultations\/c2\/infeasible$/, () => report),
      route('POST', /\/consultations$/, () => ({ ...consultation, id: 'c3', status: 'created' })),
      route('POST', /\/consultations\/c3\/builds$/, () => ({ ...consultation, id: 'c3' })),
      route('GET', /\/consultations\/c3$/, () => ({ ...consultation, id: 'c3' })),
    ]);
    renderResults('c2');

    expect(await screen.findByText('Подобрать сборку не удалось')).toBeInTheDocument();
    expect(await screen.findByText(/Минимальный класс видеокарты/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Подобрать с этим' }));

    const created = await vi.waitFor(() => {
      const call = api.calls.find((c) => c.method === 'POST' && c.path.endsWith('/consultations'));
      if (!call) throw new Error('нет запроса');
      return call;
    });
    expect(created.body).toEqual({
      answers: { tasks: { main: 'aaa_gaming' }, budget: 46000, resolution: '1080p' },
      owned_component_ids: [],
    });
  });

  it('предлагает компромиссную сборку и подбирает с уступками', async () => {
    const user = userEvent.setup();
    const infeasible = {
      ...consultation,
      id: 'c2',
      status: 'infeasible' as const,
      answers: { tasks: { main: 'aaa_gaming' }, budget: 40000 },
      builds: [],
      infeasibility: null,
    };
    const accepted = {
      ...consultation,
      id: 'c3',
      waived: [{ fact: 'req.cpu_single_min', title: 'Процессор слабее рекомендованного' }],
    };
    const api = mockApi([
      route('GET', /\/consultations\/c2$/, () => infeasible),
      route('GET', /\/consultations\/c2\/infeasible$/, () => report),
      route('POST', /\/consultations$/, () => ({ ...accepted, status: 'created' })),
      route('POST', /\/consultations\/c3\/builds$/, () => accepted),
      route('GET', /\/consultations\/c3$/, () => accepted),
    ]);
    renderResults('c2');

    expect(
      await screen.findByText('Можно собрать за ваш бюджет — с уступками'),
    ).toBeInTheDocument();
    expect(screen.getByText('SSD 500 ГБ вместо 1000')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Подобрать с этими уступками' }));

    const created = await vi.waitFor(() => {
      const call = api.calls.find((c) => c.method === 'POST' && c.path.endsWith('/consultations'));
      if (!call) throw new Error('нет запроса');
      return call;
    });
    expect(created.body).toEqual({
      answers: { tasks: { main: 'aaa_gaming' }, budget: 40000, storage_gb: 500 },
      owned_component_ids: [],
      waived_requirements: ['req.cpu_single_min'],
    });
  });

  it('напоминает об уступках в результатах', async () => {
    const waived = {
      ...consultation,
      id: 'c4',
      waived: [{ fact: 'req.cpu_single_min', title: 'Процессор слабее рекомендованного' }],
    };
    mockApi([route('GET', /\/consultations\/c4$/, () => waived)]);
    renderResults('c4');

    expect(await screen.findByText('Подобрано с уступками ради бюджета')).toBeInTheDocument();
    expect(screen.getByText('Процессор слабее рекомендованного')).toBeInTheDocument();
  });
});
