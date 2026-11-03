import { Chip, Group, Stack, Text } from '@mantine/core';

import type { QuestionOut } from '../../api/types';
import { UNKNOWN } from './answers';

interface ChoiceQuestionProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: string | number) => void;
}

/** Выбор одного варианта; «Не знаю» — если вопрос это допускает. */
export function ChoiceQuestion({ question, value, onChange }: ChoiceQuestionProps) {
  const options = question.options.map((option) => ({
    key: String(option.value),
    value: option.value,
    label: option.label,
  }));
  if (question.allow_unknown) options.push({ key: UNKNOWN, value: UNKNOWN, label: 'Не знаю' });

  return (
    <Stack gap="xs">
      <Text fw={500}>{question.title}</Text>
      <Chip.Group
        value={String(value)}
        onChange={(key) => {
          const found = options.find((option) => option.key === key);
          if (found) onChange(found.value);
        }}
      >
        <Group gap="xs">
          {options.map((option) => (
            <Chip key={option.key} value={option.key}>
              {option.label}
            </Chip>
          ))}
        </Group>
      </Chip.Group>
    </Stack>
  );
}
