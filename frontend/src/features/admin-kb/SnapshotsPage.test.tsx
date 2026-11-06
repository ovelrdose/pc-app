import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { SnapshotsPage } from './SnapshotsPage';
import { snapshotsFixture } from './testing/fixtures';

describe('SnapshotsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает список снимков с версиями, checksum и golden-отчётом', async () => {
    mockApi([route('GET', /\/api\/v1\/admin\/kb\/snapshots$/, () => snapshotsFixture)]);
    renderWithProviders(<SnapshotsPage />);

    expect(await screen.findByText('v15')).toBeInTheDocument();
    expect(screen.getByText('v14')).toBeInTheDocument();
    expect(screen.getByText('abcdef123456')).toBeInTheDocument();
    expect(screen.getByText('новые правила AM6')).toBeInTheDocument();
    expect(screen.getByText('engineer@sborshik.local')).toBeInTheDocument();
  });

  it('переиздаёт снимок только после подтверждения', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/kb\/snapshots$/, () => snapshotsFixture),
      route('POST', /\/api\/v1\/admin\/kb\/snapshots\/14\/republish$/, () => ({
        snapshot_id: 14,
        version: 16,
        created: true,
        rules: 530,
        warnings: 2,
        golden_cases: 16,
        statuses_changed: 0,
      })),
    ]);
    renderWithProviders(<SnapshotsPage />);

    // Дожидаемся обеих строк таблицы, затем жмём «Переиздать» у v14.
    await screen.findByText('v14');
    const republishButtons = await screen.findAllByRole('button', { name: /Переиздать/ });
    const second = republishButtons[1];
    expect(second).toBeDefined();
    if (!second) return;
    await user.click(second);

    // Подтверждение: в модальном окне кнопка «Переиздать».
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Переиздать' });
    await user.click(confirm);

    await waitFor(() =>
      expect(api.calls.some((call) => call.path.includes('/snapshots/14/republish'))).toBe(true),
    );
    const call = api.calls.find((call) => call.path.includes('/republish'));
    expect(call?.method).toBe('POST');
  });
});
