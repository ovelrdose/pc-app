import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Notifications } from '@mantine/notifications';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { mockApi, route } from '../../../tests/mockApi';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { KbHomePage } from './KbHomePage';
import { validateReportFixture } from './testing/fixtures';

const rulePage = (total: number) => ({ items: [], total, limit: 1, offset: 0 });

/** Лёгкий статус черновика: дешёвое чтение из БД, без компиляции и эталонных кейсов. */
const kbStatus = {
  checksum: 'abcdef1234567890fedcba0987654321abcdef1234567890fedcba0987654321',
  matches_latest: false,
  rules_total: 531,
};

function problem(
  status: number,
  code: string,
  title: string,
  detail: string,
  findings: string[],
): Response {
  return Response.json(
    { type: `https://sborshik.local/problems/${code}`, title, status, detail, findings },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );
}

function renderHome() {
  return renderWithProviders(
    <>
      <Notifications />
      <KbHomePage />
    </>,
  );
}

describe('KbHomePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('при открытии показывает лёгкий статус и не запускает полную проверку', async () => {
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => kbStatus),
      route('POST', /\/api\/v1\/admin\/kb\/validate$/, () => validateReportFixture),
    ]);
    renderHome();

    expect((await screen.findAllByText('abcdef1234567890')).length).toBeGreaterThan(0);
    expect(screen.getByText('Отличается от опубликованного')).toBeInTheDocument();
    expect(screen.getByText('531')).toBeInTheDocument();
    // Полная проверка — только по кнопке: автоматического вызова при монтировании нет.
    expect(api.calls.some((call) => call.path.includes('/validate'))).toBe(false);
    expect(screen.queryByText(/Ошибки \(2\)/)).not.toBeInTheDocument();
  });

  it('по кнопке «Проверить» запускает полную проверку и показывает отчёт', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => kbStatus),
      route('POST', /\/api\/v1\/admin\/kb\/validate$/, () => validateReportFixture),
    ]);
    renderHome();

    await screen.findAllByText('abcdef1234567890');
    expect(api.calls.some((call) => call.path.includes('/validate'))).toBe(false);

    await user.click(screen.getByRole('button', { name: /Проверить/ }));

    expect(await screen.findByText(/Ошибки \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/CMP-012: слот `lenght_mm` не существует/)).toBeInTheDocument();
    expect(
      api.calls.filter((call) => call.method === 'POST' && call.path.includes('/validate')),
    ).toHaveLength(1);
  });

  it('повторный клик во время проверки не запускает её дважды', async () => {
    const user = userEvent.setup();
    let releaseValidate: ((report: typeof validateReportFixture) => void) | undefined;
    const gate = new Promise<typeof validateReportFixture>((resolve) => {
      releaseValidate = resolve;
    });
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => kbStatus),
      route('POST', /\/api\/v1\/admin\/kb\/validate$/, () => gate),
    ]);
    renderHome();

    await screen.findAllByText('abcdef1234567890');
    const validateCalls = () =>
      api.calls.filter((call) => call.method === 'POST' && call.path.includes('/validate'));

    const button = screen.getByRole('button', { name: /Проверить/ });
    await user.click(button);
    await waitFor(() => expect(validateCalls()).toHaveLength(1));

    // Кнопка уже в loading, но даже «программный» повторный клик не должен дать второй запрос.
    fireEvent.click(button);
    expect(validateCalls()).toHaveLength(1);

    releaseValidate?.(validateReportFixture);
    expect(await screen.findByText(/Ошибки \(2\)/)).toBeInTheDocument();
  });

  it('пока идёт проверка, кнопка публикации заблокирована', async () => {
    const user = userEvent.setup();
    let releaseValidate: ((report: typeof validateReportFixture) => void) | undefined;
    const gate = new Promise<typeof validateReportFixture>((resolve) => {
      releaseValidate = resolve;
    });
    mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => kbStatus),
      route('POST', /\/api\/v1\/admin\/kb\/validate$/, () => gate),
    ]);
    renderHome();

    await screen.findAllByText('abcdef1234567890');
    await user.click(screen.getByRole('button', { name: /Проверить/ }));

    expect(screen.getByRole('button', { name: /Опубликовать/ })).toBeDisabled();

    releaseValidate?.(validateReportFixture);
    await screen.findByText(/Ошибки \(2\)/);
    await waitFor(() => expect(screen.getByRole('button', { name: /Опубликовать/ })).toBeEnabled());
  });

  it('публикация: 409 kb-invalid показывает title и findings в модальном окне', async () => {
    const user = userEvent.setup();
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => kbStatus),
      route('POST', /\/api\/v1\/admin\/kb\/publish$/, () =>
        problem(
          409,
          'kb-invalid',
          'База знаний не прошла проверку',
          'В черновике 2 ошибок проверки',
          [
            'CMP-012: слот `lenght_mm` не существует во фрейме «Видеокарта»',
            'PRF-011 → REQ-007 → PRF-011: цикл',
          ],
        ),
      ),
    ]);
    renderHome();

    await screen.findAllByText('abcdef1234567890');
    await user.click(screen.getByRole('button', { name: /Опубликовать/ }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Опубликовать' }));

    expect(await within(dialog).findByText(/База знаний не прошла проверку/)).toBeInTheDocument();
    expect(within(dialog).getByText(/CMP-012: слот `lenght_mm` не существует/)).toBeInTheDocument();
    expect(within(dialog).getByText(/PRF-011 → REQ-007 → PRF-011: цикл/)).toBeInTheDocument();

    await waitFor(() =>
      expect(api.calls.some((call) => call.path.includes('/publish'))).toBe(true),
    );
  });

  it('успешная публикация показывает версию снимка и обновляет статус без полной проверки', async () => {
    const user = userEvent.setup();
    let matchesLatest = false;
    const api = mockApi([
      route('GET', /\/api\/v1\/admin\/rules$/, () => rulePage(531)),
      route('GET', /\/api\/v1\/admin\/kb\/status$/, () => ({
        ...kbStatus,
        matches_latest: matchesLatest,
      })),
      route('POST', /\/api\/v1\/admin\/kb\/publish$/, () => ({
        snapshot_id: 15,
        version: 15,
        created: true,
        rules: 531,
        warnings: 1,
        golden_cases: 16,
        statuses_changed: 2,
      })),
    ]);
    renderHome();

    await screen.findAllByText('abcdef1234567890');
    expect(screen.getByText('Отличается от опубликованного')).toBeInTheDocument();

    // После публикации сервер считает черновик совпадающим со снимком.
    matchesLatest = true;

    await user.click(screen.getByRole('button', { name: /Опубликовать/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/Комментарий/), 'правка правил бюджета');
    await user.click(within(dialog).getByRole('button', { name: 'Опубликовать' }));

    expect(await screen.findByText(/Опубликован снимок v15/)).toBeInTheDocument();
    expect(await screen.findByText('Совпадает с опубликованным')).toBeInTheDocument();
    // Публикация не дёргает тяжёлую проверку — только лёгкий статус обновился.
    expect(api.calls.some((call) => call.path.includes('/validate'))).toBe(false);
  });
});
