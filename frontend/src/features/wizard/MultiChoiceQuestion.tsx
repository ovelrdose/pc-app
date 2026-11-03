import { MultiSelect } from '@mantine/core';

import type { QuestionOut } from '../../api/types';

interface MultiChoiceQuestionProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: string[]) => void;
}

/** Выбор нескольких вариантов с поиском (игры, программы). */
export function MultiChoiceQuestion({ question, value, onChange }: MultiChoiceQuestionProps) {
  const selected = Array.isArray(value) ? value.map(String) : [];
  return (
    <MultiSelect
      label={question.title}
      placeholder={selected.length === 0 ? 'Можно пропустить' : undefined}
      data={question.options.map((option) => ({
        value: String(option.value),
        label: option.label,
      }))}
      value={selected}
      onChange={onChange}
      searchable
      clearable
      nothingFoundMessage="Ничего не найдено"
    />
  );
}
