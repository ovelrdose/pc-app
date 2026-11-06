import '../../../tests/mockMonaco';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { RuleTestPage } from './RuleTestPage';
import { ruleDetailFixture, ruleTestResultFixture } from './testing/fixtures';

function renderTestPage(code = 'BUD-014') {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/kb/rules/:code/test" element={<RuleTestPage />} />
    </Routes>,
    { route: `/admin/kb/rules/${code}/test` },
  );
}

describe('RuleTestPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('отправляет факты и показывает результат прогона (matched, действия, факты)', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules\/BUD-014$/, () => ruleDetailFixture()),
      route('POST', /\/api\/v1\/admin\/rules\/BUD-014\/test$/, () => ruleTestResultFixture),
    ]);
    renderTestPage();

    expect(await screen.findByText('Проверка правила BUD-014')).toBeInTheDocument();
    expect(await screen.findByText(/4K-гейминг смещает бюджет в видеокарту/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Запустить/ }));

    expect(await screen.findByText('Сработало')).toBeInTheDocument();
    expect(screen.getByText(/CF посылки/)).toBeInTheDocument();
    expect(screen.getAllByText('budget.share.gpu').length).toBeGreaterThan(0);
    expect(screen.getAllByText('budget.share.cpu').length).toBeGreaterThan(0);
    expect(screen.getByText('Факты после прогона')).toBeInTheDocument();

    const testCall = api.calls.find((call) => call.path.endsWith('/test'));
    expect(testCall).toBeDefined();
    expect(testCall?.body).toEqual({
      facts: { 'user.budget': 90000, 'user.resolution': '1080p' },
    });
  });

  it('объясняет, что goal-правила тестируются на сборке (422)', async () => {
    const user = userEvent.setup();
    const goalRule = ruleDetailFixture();
    goalRule.rule.kind = 'goal';
    goalRule.rule.body = {
      ...goalRule.rule.body,
      kind: 'goal',
      when: { goal: { predicate: 'fps_at_least', args: {} } },
    };
    mockApi([
      route('GET', /\/api\/v1\/admin\/rules\/GOL-GENERAL$/, () => goalRule),
      route('POST', /\/api\/v1\/admin\/rules\/GOL-GENERAL\/test$/, () =>
        Response.json(
          {
            type: 'https://sborshik.local/problems/goal-rule-test-unsupported',
            title: 'Goal-правила тестируются на сборке',
            status: 422,
            detail: 'Подцели требуют обратного вывода с готовой сборкой.',
          },
          { status: 422, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    ]);
    renderTestPage('GOL-GENERAL');

    expect(
      await screen.findByText(/Для целей обратного вывода изолированный прогон не поддерживается/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Запустить/ }));
    expect(await screen.findByText('Прогон неприменим')).toBeInTheDocument();
    expect(await screen.findByText(/подцели требуют обратного вывода/i)).toBeInTheDocument();
  });

  it('показывает ошибку разбора фактов, не дёргая сервер', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules\/BUD-014$/, () => ruleDetailFixture()),
    ]);
    renderTestPage();

    const editor = await screen.findByRole('textbox', { name: 'Входные факты' });
    fireEvent.change(editor, { target: { value: 'a: [1,' } });

    await user.click(screen.getByRole('button', { name: /Запустить/ }));
    expect(await screen.findByText('Факты не разобраны')).toBeInTheDocument();
    await waitFor(() =>
      expect(api.calls.filter((call) => call.path.endsWith('/test'))).toHaveLength(0),
    );
  });
});
