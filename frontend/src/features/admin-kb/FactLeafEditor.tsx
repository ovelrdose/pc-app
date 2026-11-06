import { Button, Group, MultiSelect, NumberInput, Select, TextInput } from '@mantine/core';

import type { FactCondition, Op, Scalar, VocabularyOut } from '../../api/types';
import { leafUsesRef, opNeedsValue, opsForFact } from './conditions';
import { FACT_TYPE_TITLES } from './labels';

interface ConditionValueInputProps {
  fact: VocabularyOut;
  op: Op;
  value: Scalar | Scalar[] | null | undefined;
  onChange: (value: Scalar | Scalar[] | null) => void;
  disabled: boolean;
}

/** Значение листа по типу факта: число / диапазон / да-нет / выбор из списка / строка. */
export function ConditionValueInput({
  fact,
  op,
  value,
  onChange,
  disabled,
}: ConditionValueInputProps) {
  if (!opNeedsValue(op)) return null;

  if (op === 'between') {
    const pair: unknown[] = Array.isArray(value) ? value : [];
    return (
      <Group gap="xs" wrap="nowrap">
        <NumberInput
          aria-label="От"
          placeholder="от"
          w={110}
          value={typeof pair[0] === 'number' ? pair[0] : ''}
          onChange={(next) =>
            onChange([
              typeof next === 'number' ? next : 0,
              typeof pair[1] === 'number' ? pair[1] : 0,
            ])
          }
          disabled={disabled}
        />
        <NumberInput
          aria-label="До"
          placeholder="до"
          w={110}
          value={typeof pair[1] === 'number' ? pair[1] : ''}
          onChange={(next) =>
            onChange([
              typeof pair[0] === 'number' ? pair[0] : 0,
              typeof next === 'number' ? next : 0,
            ])
          }
          disabled={disabled}
        />
      </Group>
    );
  }

  switch (fact.type) {
    case 'number': {
      const numeric = typeof value === 'number' ? value : 0;
      return (
        <NumberInput
          aria-label="Значение"
          placeholder="значение"
          w={140}
          value={numeric}
          onChange={(next) => onChange(typeof next === 'number' ? next : 0)}
          disabled={disabled}
        />
      );
    }
    case 'bool':
      return (
        <Select
          aria-label="Значение"
          w={130}
          data={[
            { value: 'true', label: 'да' },
            { value: 'false', label: 'нет' },
          ]}
          value={value === false ? 'false' : 'true'}
          onChange={(next) => onChange(next === 'false' ? false : true)}
          disabled={disabled}
          allowDeselect={false}
        />
      );
    case 'str':
      if (fact.values.length > 0) {
        const options = fact.values.map((item) => String(item));
        if (op === 'in' || op === 'not_in') {
          const selected = Array.isArray(value) ? value.map(String) : [];
          return (
            <MultiSelect
              aria-label="Значения"
              placeholder="выберите значения"
              data={options}
              value={selected}
              onChange={(next) => onChange(next)}
              disabled={disabled}
            />
          );
        }
        return (
          <Select
            aria-label="Значение"
            placeholder="выберите значение"
            data={options}
            value={value === undefined || value === null ? null : String(value)}
            onChange={(next) => onChange(next)}
            disabled={disabled}
            clearable={false}
          />
        );
      }
      return (
        <TextInput
          aria-label="Значение"
          placeholder="значение"
          w={200}
          value={typeof value === 'string' ? value : ''}
          onChange={(event) => onChange(event.currentTarget.value)}
          disabled={disabled}
        />
      );
    default: {
      // list: значения через запятую
      const text = Array.isArray(value)
        ? value.join(', ')
        : value === undefined || value === null
          ? ''
          : String(value);
      return (
        <TextInput
          aria-label="Значения"
          placeholder="через запятую"
          w={220}
          value={text}
          onChange={(event) =>
            onChange(
              event.currentTarget.value
                .split(',')
                .map((item) => item.trim())
                .filter((item) => item.length > 0),
            )
          }
          disabled={disabled}
        />
      );
    }
  }
}

interface FactLeafEditorProps {
  leaf: FactCondition;
  onChange: (leaf: FactCondition) => void;
  vocabulary: VocabularyOut[];
  disabled: boolean;
}

/** Лист-условие: выбор факта из словаря, оператор по типу, значение или ссылка на факт. */
export function FactLeafEditor({ leaf, onChange, vocabulary, disabled }: FactLeafEditorProps) {
  const fact = vocabulary.find((item) => item.path === leaf.fact);
  const ops = opsForFact(fact);
  const op: Op = ops.includes(leaf.op) ? leaf.op : (ops[0] ?? 'eq');
  const usesRef = leafUsesRef(leaf);

  const factOptions = vocabulary.map((item) => ({
    value: item.path,
    label: `${item.path} — ${item.title} (${FACT_TYPE_TITLES[item.type] ?? item.type})`,
  }));

  const updateOp = (nextOp: Op) => {
    if (!opNeedsValue(nextOp)) {
      onChange({ fact: leaf.fact, op: nextOp, value: null, ref: null });
      return;
    }
    if (usesRef) {
      onChange({ fact: leaf.fact, op: nextOp, value: null, ref: leaf.ref ?? null });
      return;
    }
    onChange({ fact: leaf.fact, op: nextOp, value: leaf.value ?? null, ref: null });
  };

  return (
    <Group gap="xs" wrap="wrap" align="flex-end">
      <Select
        aria-label="Факт"
        placeholder="факт"
        searchable
        w={300}
        data={factOptions}
        value={leaf.fact}
        onChange={(next) => next && onChange({ ...leaf, fact: next })}
        disabled={disabled}
      />
      <Select
        aria-label="Оператор"
        w={150}
        data={ops.map((item) => ({ value: item, label: item }))}
        value={op}
        onChange={(next) => next && updateOp(next as Op)}
        disabled={disabled}
        allowDeselect={false}
      />
      {opNeedsValue(op) && fact ? (
        <Group gap="xs" wrap="nowrap" align="flex-end">
          {usesRef ? (
            <Select
              aria-label="Факт для сравнения"
              placeholder="другой факт"
              searchable
              w={300}
              data={factOptions}
              value={leaf.ref ?? null}
              onChange={(next) => onChange({ ...leaf, ref: next ?? null })}
              disabled={disabled}
            />
          ) : (
            <ConditionValueInput
              fact={fact}
              op={op}
              value={leaf.value}
              onChange={(next) => onChange({ ...leaf, value: next })}
              disabled={disabled}
            />
          )}
          <Button
            size="compact-sm"
            variant={usesRef ? 'filled' : 'default'}
            onClick={() =>
              onChange(
                usesRef
                  ? { ...leaf, ref: null, value: null }
                  : { ...leaf, value: null, ref: vocabulary[0]?.path ?? '' },
              )
            }
            disabled={disabled}
            title="Сравнить со значением другого факта"
          >
            {usesRef ? 'факт ✓' : 'факт'}
          </Button>
        </Group>
      ) : null}
    </Group>
  );
}
