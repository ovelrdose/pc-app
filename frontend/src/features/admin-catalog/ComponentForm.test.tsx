import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ComponentForm } from './ComponentForm';
import { frameFields, initialValues } from './frames';
import { cpuFrame } from './testing/frames';

/** jsdom не делает неявную отправку формы по клику на submit-кнопку — шлём событие напрямую. */
function submitForm() {
  const form = document.querySelector('form');
  expect(form).not.toBeNull();
  fireEvent.submit(form!);
}

function setup(prefill: Record<string, string | number | boolean> = {}) {
  const fields = frameFields(cpuFrame);
  const values = { ...initialValues('cpu', fields), ...prefill };
  const onSubmit = vi.fn();
  renderWithProviders(
    <ComponentForm
      frame={cpuFrame}
      values={values}
      submitLabel="Создать"
      busy={false}
      onSubmit={onSubmit}
    />,
  );
  return { onSubmit };
}

describe('ComponentForm', () => {
  it('показывает поля из фрейма и рождает валидное тело CPU', async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup({
      brand: 'AMD',
      model: 'Ryzen 5 7600',
      cores: 6,
      threads: 12,
      base_ghz: 3.8,
      boost_ghz: 5.1,
      tdp_w: 105,
      mem_types: 'DDR5',
    });

    // Поля построены из JSON Schema фрейма: строки, числа, enum из $defs, переключатели.
    expect(screen.getByRole('textbox', { name: 'Артикул' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Ядер' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Цвет' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Встроенная графика' })).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: 'Артикул' }), 'R5-7600');
    await user.type(screen.getByRole('textbox', { name: 'Цена' }), '18990');
    await user.type(screen.getByRole('textbox', { name: 'Сокет' }), 'AM5');
    await user.click(screen.getByRole('switch', { name: 'Встроенная графика' }));
    submitForm();

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        category: 'cpu',
        sku: 'R5-7600',
        brand: 'AMD',
        model: 'Ryzen 5 7600',
        price_kop: 1_899_000,
        socket: 'AM5',
        cores: 6,
        threads: 12,
        base_ghz: 3.8,
        boost_ghz: 5.1,
        tdp_w: 105,
        igpu: true,
        mem_types: ['DDR5'],
        color: 'black',
        in_stock: true,
      }),
    );
  });

  it('не отправляет форму с незаполненными обязательными полями', async () => {
    const { onSubmit } = setup();
    submitForm();

    await waitFor(() => expect(screen.getAllByText(/Заполните поле/).length).toBeGreaterThan(0));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('ловит нарушение паттерна артикула', async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup({
      brand: 'AMD',
      model: '7600',
      price_kop: 1000,
      socket: 'AM5',
      cores: 6,
      threads: 12,
      base_ghz: 3.8,
      boost_ghz: 5.1,
      tdp_w: 105,
      mem_types: 'DDR5',
      igpu: true,
    });
    await user.type(screen.getByRole('textbox', { name: 'Артикул' }), 'r5 7600');
    submitForm();

    expect(await screen.findByText(/Недопустимое значение для «Артикул»/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
