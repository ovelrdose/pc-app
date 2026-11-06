import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ConditionNode } from '../../api/types';
import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ConditionTreeEditor } from './ConditionTreeEditor';
import { vocabularyFixture } from './testing/fixtures';

function Harness({
  initial,
  onChange,
}: {
  initial: ConditionNode;
  onChange: (node: ConditionNode) => void;
}) {
  const [node, setNode] = useState<ConditionNode>(initial);
  return (
    <ConditionTreeEditor
      node={node}
      vocabulary={vocabularyFixture}
      onChange={(next) => {
        setNode(next);
        onChange(next);
      }}
    />
  );
}

function setup(initial: ConditionNode) {
  const onChange = vi.fn();
  renderWithProviders(<Harness initial={initial} onChange={onChange} />);
  return { onChange };
}

describe('ConditionTreeEditor', () => {
  it('переключает группу all → any и обратно', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ all: [{ fact: 'user.budget', op: 'gt', value: 0 }] });

    await user.click(screen.getByRole('textbox', { name: 'Тип группы' }));
    await user.click(await screen.findByRole('option', { name: 'Любое из (ИЛИ)' }));
    expect(onChange).toHaveBeenLastCalledWith({
      any: [{ fact: 'user.budget', op: 'gt', value: 0 }],
    });
  });

  it('добавляет условие, группу и отрицание; удаляет дочерний узел', async () => {
    const user = userEvent.setup();
    const { onChange } = setup({ all: [] });

    await user.click(screen.getByRole('button', { name: 'Условие' }));
    expect(onChange).toHaveBeenLastCalledWith({
      all: [{ fact: 'user.budget', op: 'eq', value: 0, ref: null }],
    });

    // Отрицание добавляем до вложенной группы, чтобы кнопки не дублировались.
    await user.click(screen.getByRole('button', { name: 'Не' }));
    expect(onChange).toHaveBeenLastCalledWith({
      all: [
        { fact: 'user.budget', op: 'eq', value: 0, ref: null },
        { not: { fact: 'user.budget', op: 'eq', value: 0, ref: null } },
      ],
    });

    await user.click(screen.getByRole('button', { name: 'Группа' }));
    const lastCall = onChange.mock.calls.at(-1)?.[0] as { all: unknown[] };
    expect(lastCall.all).toHaveLength(3);
    expect(lastCall.all[2]).toEqual({ all: [] });

    await user.click(screen.getByRole('button', { name: 'Удалить условие 3' }));
    const afterDelete = onChange.mock.calls.at(-1)?.[0] as { all: unknown[] };
    expect(afterDelete.all).toHaveLength(2);
  });

  it('показывает подсказку для expr-листа и не даёт его править', () => {
    setup({ all: [{ expr: 'build.psu.wattage < 500' }] });
    expect(screen.getByText('Выражение (expr)')).toBeInTheDocument();
    expect(screen.getByText(/конструктор его не правит/)).toBeInTheDocument();
    expect(screen.getByText('build.psu.wattage < 500')).toBeInTheDocument();
  });

  it('строковый факт со списком значений предлагает оператор in', async () => {
    const user = userEvent.setup();
    setup({ all: [{ fact: 'user.resolution', op: 'in', value: ['1080p'] }] });

    // Выбор значения из списка допустимых значений словаря
    await user.click(screen.getByRole('textbox', { name: 'Значения' }));
    expect(await screen.findByRole('option', { name: '1440p' })).toBeInTheDocument();
  });

  it('лист со ссылкой на факт (ref) переключается кнопкой', async () => {
    const user = userEvent.setup();
    setup({ all: [{ fact: 'user.budget', op: 'eq', value: 100, ref: null }] });

    await user.click(screen.getByRole('button', { name: 'факт' }));
    const editor = screen.getByRole('textbox', { name: 'Факт для сравнения' });
    expect(editor).toBeInTheDocument();
  });
});
