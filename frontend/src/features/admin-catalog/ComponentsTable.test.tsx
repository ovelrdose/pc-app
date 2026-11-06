import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ComponentOut } from '../../api/types';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ComponentsTable } from './ComponentsTable';

function component(
  partial: Partial<ComponentOut> & Pick<ComponentOut, 'id' | 'name' | 'status'>,
): ComponentOut {
  return {
    sku: `SKU-${partial.id}`,
    category: 'cpu',
    brand: 'AMD',
    model: partial.name,
    price_kop: 100_000,
    price_checked_at: null,
    price_note: null,
    in_stock: true,
    source: 'manual',
    status_issues: [],
    specs: {},
    perf: {},
    ...partial,
  };
}

const items: ComponentOut[] = [
  component({
    id: 'c1',
    name: 'AMD Ryzen 5 7600',
    status: 'needs_kb',
    status_issues: ['сокет AM6 отсутствует в sockets'],
  }),
  component({ id: 'c2', name: 'AMD Ryzen 7 7700', status: 'active' }),
  component({ id: 'c3', name: 'Intel Core i5-14400F', status: 'inactive', in_stock: false }),
];

function setup() {
  const onToggleStock = vi.fn();
  const onChangeStatus = vi.fn();
  renderWithProviders(
    <ComponentsTable
      items={items}
      onToggleStock={onToggleStock}
      onChangeStatus={onChangeStatus}
      busy={false}
    />,
  );
  return { onToggleStock, onChangeStatus };
}

describe('ComponentsTable', () => {
  it('показывает бейджи статусов и причины по наведению', async () => {
    const user = userEvent.setup();
    setup();

    expect(screen.getByText('Требует знаний')).toBeInTheDocument();
    expect(screen.getByText('Активен')).toBeInTheDocument();
    expect(screen.getByText('Неактивен')).toBeInTheDocument();

    await user.hover(screen.getByText('Требует знаний'));
    expect(await screen.findByText('сокет AM6 отсутствует в sockets')).toBeInTheDocument();
  });

  it('переключает наличие и снимает с продажи через меню', async () => {
    const user = userEvent.setup();
    const { onToggleStock, onChangeStatus } = setup();

    await user.click(screen.getByRole('switch', { name: 'В наличии: AMD Ryzen 7 7700' }));
    expect(onToggleStock).toHaveBeenCalledWith(expect.objectContaining({ id: 'c2' }), false);

    await user.click(screen.getByLabelText('Действия: AMD Ryzen 7 7700'));
    await user.click(await screen.findByText('Снять с продажи'));
    await waitFor(() =>
      expect(onChangeStatus).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'c2' }),
        'inactive',
      ),
    );
  });

  it('неактивному предлагает вернуть к продаже, а не снять', async () => {
    const user = userEvent.setup();
    const { onChangeStatus } = setup();

    await user.click(screen.getByLabelText('Действия: Intel Core i5-14400F'));
    await user.click(await screen.findByText('Вернуть к продаже'));
    await waitFor(() =>
      expect(onChangeStatus).toHaveBeenCalledWith(expect.objectContaining({ id: 'c3' }), 'active'),
    );
  });
});
