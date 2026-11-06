import '../../../tests/mockMonaco';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Notifications } from '@mantine/notifications';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { RuleEditorPage } from './RuleEditorPage';
import { ruleDetailFixture, ruleOut, vocabularyFixture } from './testing/fixtures';

function renderEditor(path: string) {
  return renderWithProviders(
    <>
      <Notifications />
      <Routes>
        <Route path="/admin/kb/rules/new" element={<RuleEditorPage />} />
        <Route path="/admin/kb/rules/:code" element={<RuleEditorPage />} />
        <Route path="/admin/kb/rules" element={<div>список правил</div>} />
      </Routes>
    </>,
    { route: path },
  );
}

function problem(status: number, code: string, title: string, detail: string): Response {
  return Response.json(
    { type: `https://sborshik.local/problems/${code}`, title, status, detail },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

const vocabularyRoute = () =>
  route('GET', /\/api\/v1\/admin\/kb\/vocabulary$/, () => vocabularyFixture);

describe('RuleEditorPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('блокирует сохранение с пустой метой и не дёргает сервер', async () => {
    const user = userEvent.setup();
    const api = mockApi([vocabularyRoute()]);
    renderEditor('/admin/kb/rules/new');

    await user.click(await screen.findByRole('button', { name: /Сохранить/ }));

    expect(await screen.findByText('Правило не сохранено')).toBeInTheDocument();
    expect(screen.getByText(/Укажите код правила/)).toBeInTheDocument();
    await waitFor(() => expect(api.calls.filter((call) => call.method === 'POST')).toHaveLength(0));
  });

  it('создаёт правило из конструктора и переходит на его карточку', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      vocabularyRoute(),
      route('POST', /\/api\/v1\/admin\/rules$/, () => ruleOut({ code: 'REQ-100' })),
      route('GET', /\/api\/v1\/admin\/rules\/REQ-100$/, () => ({
        rule: ruleOut({ code: 'REQ-100' }),
        revisions: [],
      })),
    ]);
    renderEditor('/admin/kb/rules/new');

    const fill = async (name: string, value: string) => {
      fireEvent.change(await screen.findByRole('textbox', { name }), { target: { value } });
    };
    await fill('Код', 'REQ-100');
    await fill('Название', 'Нужен Wi-Fi');
    await fill('Группа', 'requirements');
    await fill('Объяснение (explain)', 'Тестовое.');
    await user.click(screen.getByRole('button', { name: /Сохранить/ }));

    await waitFor(() => {
      const post = api.calls.find((call) => call.method === 'POST');
      expect(post).toBeDefined();
      expect(post?.body).toMatchObject({
        code: 'REQ-100',
        name: 'Нужен Wi-Fi',
        kind: 'inference',
        group: 'requirements',
        explain: 'Тестовое.',
        origin: 'manual',
        when: { all: [{ fact: 'user.budget', op: 'gt', value: 0, ref: null }] },
      });
    });
    // после создания — переход на карточку нового кода
    expect(await screen.findByRole('heading', { name: 'REQ-100' })).toBeInTheDocument();
  });

  it('для сгенерированного правила показывает бейдж и предупреждение об override', async () => {
    const generated = ruleOut({
      code: 'GEN-SKT-AM5-MEM',
      origin: 'generated',
      source: 'tables/sockets.yaml#AM5',
      body: {
        code: 'GEN-SKT-AM5-MEM',
        name: 'Память платформы AM5',
        kind: 'compat',
        group: 'compatibility',
        priority: 900,
        cf: 1,
        enabled: true,
        origin: 'generated',
        source: 'tables/sockets.yaml#AM5',
        when: { fact: 'cand.mem_type', op: 'eq', value: 'DDR5' },
        then: [{ action: 'reject', message: 'AM5 работает только с DDR5' }],
        explain: 'Сгенерировано из справочника сокетов.',
      },
    });
    mockApi([
      vocabularyRoute(),
      route('GET', /\/api\/v1\/admin\/rules\/GEN-SKT-AM5-MEM$/, () => ({
        rule: generated,
        revisions: [],
      })),
    ]);
    renderEditor('/admin/kb/rules/GEN-SKT-AM5-MEM');

    expect(await screen.findByText('Сгенерировано')).toBeInTheDocument();
    expect(screen.getByText(/Ручная правка переведёт его в «ручные»/)).toBeInTheDocument();
  });

  it('YAML-вкладка сериализует тело, синтаксическая ошибка блокирует сохранение', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      vocabularyRoute(),
      route('GET', /\/api\/v1\/admin\/rules\/BUD-014$/, () => ruleDetailFixture()),
    ]);
    renderEditor('/admin/kb/rules/BUD-014');

    await user.click(await screen.findByRole('tab', { name: 'YAML' }));
    const editor = (await screen.findByRole('textbox', {
      name: 'Тело правила в YAML',
    })) as HTMLTextAreaElement;
    expect(editor.value).toContain('code: BUD-014');

    editor.value = '';
    fireEvent.change(editor, { target: { value: 'a: [1,' } });
    await user.click(screen.getByRole('button', { name: /Сохранить/ }));

    expect(await screen.findByText('Ошибка синтаксиса YAML')).toBeInTheDocument();
    await waitFor(() => expect(api.calls.filter((call) => call.method === 'PUT')).toHaveLength(0));
  });

  it('409 от сервера при создании показывает уведомление с текстом проблемы', async () => {
    const user = userEvent.setup();
    mockApi([
      vocabularyRoute(),
      route('POST', /\/api\/v1\/admin\/rules$/, () =>
        problem(409, 'rule-exists', 'Код правила занят', 'Правило REQ-100 уже есть'),
      ),
    ]);
    renderEditor('/admin/kb/rules/new');

    const fill = async (name: string, value: string) => {
      fireEvent.change(await screen.findByRole('textbox', { name }), { target: { value } });
    };
    await fill('Код', 'REQ-100');
    await fill('Название', 'Нужен Wi-Fi');
    await fill('Группа', 'requirements');
    await fill('Объяснение (explain)', 'Тестовое.');
    await user.click(screen.getByRole('button', { name: /Сохранить/ }));

    expect(await screen.findByText('Ошибка')).toBeInTheDocument();
    expect(
      await screen.findByText(/Код правила занят: Правило REQ-100 уже есть/),
    ).toBeInTheDocument();
  });
});
