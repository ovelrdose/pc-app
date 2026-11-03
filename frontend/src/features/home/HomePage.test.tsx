import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../../tests/renderWithProviders';
import { HomePage } from './HomePage';

describe('HomePage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('показывает, что сервер на связи', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ status: 'ok' })),
    );
    renderWithProviders(<HomePage />);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Соберём компьютер');
    expect(await screen.findByText('Сервер на связи')).toBeInTheDocument();
  });

  it('сообщает, если сервер недоступен', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 503 })),
    );
    renderWithProviders(<HomePage />);

    expect(await screen.findByText('Сервер недоступен')).toBeInTheDocument();
  });
});
