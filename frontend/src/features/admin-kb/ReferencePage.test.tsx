import '../../../tests/mockMonaco';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ReferencePage } from './ReferencePage';
import { regenerateFixture } from './testing/fixtures';

const referenceList = {
  sockets: { sockets: { AM5: { mem_types: ['DDR5'] } } },
  chipsets: { chipsets: { B650: { socket: 'AM5' } } },
  form_factors: { atx: { psu: 'atx' } },
  games: { games: { cyberpunk_2077: { title: 'Cyberpunk 2077' } } },
  applications: { applications: { blender: { title: 'Blender' } } },
  questionnaire: { steps: [] },
  golden: [{ id: 'G-001', title: 'Офис', answers: {}, expect: {} }],
};

describe('ReferencePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает список имён и YAML выбранного справочника', async () => {
    mockApi([
      route('GET', /\/api\/v1\/admin\/reference$/, () => referenceList),
      route('GET', /\/api\/v1\/admin\/reference\/sockets$/, () => ({
        name: 'sockets',
        data: referenceList.sockets,
      })),
    ]);
    renderWithProviders(<ReferencePage />);

    expect(await screen.findByText('Сокеты')).toBeInTheDocument();
    expect(screen.getByText('Анкета визарда')).toBeInTheDocument();
    expect(screen.getByText('Эталонные кейсы')).toBeInTheDocument();

    const editor = (await screen.findByRole('textbox', {
      name: 'Справочник Сокеты в YAML',
    })) as HTMLTextAreaElement;
    expect(editor.value).toContain('AM5');
  });

  it('сохраняет справочник целиком (PUT с разобранным YAML)', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/reference$/, () => referenceList),
      route('GET', /\/api\/v1\/admin\/reference\/sockets$/, () => ({
        name: 'sockets',
        data: referenceList.sockets,
      })),
      route('PUT', /\/api\/v1\/admin\/reference\/sockets$/, () => ({ ok: true })),
    ]);
    renderWithProviders(<ReferencePage />);

    const editor = await screen.findByRole('textbox', { name: 'Справочник Сокеты в YAML' });
    fireEvent.change(editor, {
      target: { value: 'sockets:\n  AM6:\n    mem_types:\n      - DDR5\n' },
    });
    await user.click(screen.getByRole('button', { name: /Сохранить/ }));

    await waitFor(() => {
      const put = api.calls.find((call) => call.method === 'PUT');
      expect(put).toBeDefined();
      expect(put?.body).toEqual({ sockets: { AM6: { mem_types: ['DDR5'] } } });
    });
  });

  it('не отправляет YAML с синтаксической ошибкой', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/reference$/, () => referenceList),
      route('GET', /\/api\/v1\/admin\/reference\/sockets$/, () => ({
        name: 'sockets',
        data: referenceList.sockets,
      })),
    ]);
    renderWithProviders(<ReferencePage />);

    const editor = await screen.findByRole('textbox', { name: 'Справочник Сокеты в YAML' });
    fireEvent.change(editor, { target: { value: 'a: [1,' } });
    await user.click(screen.getByRole('button', { name: /Сохранить/ }));

    expect(await screen.findByText('Ошибка синтаксиса YAML')).toBeInTheDocument();
    await waitFor(() => expect(api.calls.filter((call) => call.method === 'PUT')).toHaveLength(0));
  });

  it('показывает подсказки для анкеты и эталонных кейсов', async () => {
    const user = userEvent.setup();
    mockApi([
      route('GET', /\/api\/v1\/admin\/reference$/, () => referenceList),
      route('GET', /\/api\/v1\/admin\/reference\/sockets$/, () => ({
        name: 'sockets',
        data: referenceList.sockets,
      })),
      route('GET', /\/api\/v1\/admin\/reference\/golden$/, () => ({
        name: 'golden',
        data: referenceList.golden,
      })),
    ]);
    renderWithProviders(<ReferencePage />);

    await user.click(await screen.findByText('Эталонные кейсы'));
    expect(
      await screen.findByText(/Эталонные кейсы: список объектов \{id, title, answers, expect\}/),
    ).toBeInTheDocument();
  });

  it('регенерация: предпросмотр diff, затем применение', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/reference$/, () => referenceList),
      route('GET', /\/api\/v1\/admin\/reference\/sockets$/, () => ({
        name: 'sockets',
        data: referenceList.sockets,
      })),
      route('POST', /\/api\/v1\/admin\/reference\/regenerate$/, (request) => {
        const dryRun = new URL(request.url).searchParams.get('dry_run') !== 'false';
        return { ...regenerateFixture, dry_run: dryRun };
      }),
    ]);
    renderWithProviders(<ReferencePage />);

    await user.click(await screen.findByRole('button', { name: /Предпросмотр \(dry-run\)/ }));

    expect(await screen.findByText('GEN-GAME-GTA6-ULTRA')).toBeInTheDocument();
    expect(screen.getByText('GEN-CHP-B950-TDP')).toBeInTheDocument();
    expect(screen.getByText(/GEN-SKT-AM5-FUTURE/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Применить/ }));
    await waitFor(() => {
      const apply = api.calls.find(
        (call) => call.method === 'POST' && call.path.includes('dry_run=false'),
      );
      expect(apply).toBeDefined();
    });
  });
});
