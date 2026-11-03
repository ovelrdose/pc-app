import { SegmentedControl, Stack, Text } from '@mantine/core';

import type { QuestionOut } from '../../api/types';
import { UNKNOWN } from './answers';

const OPTIONS = [
  { value: 'yes', label: 'Да' },
  { value: 'rather_yes', label: 'Скорее да' },
  { value: UNKNOWN, label: 'Не знаю' },
  { value: 'rather_no', label: 'Скорее нет' },
  { value: 'no', label: 'Нет' },
];

interface YesNoQuestionProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: string) => void;
}

/** Вопрос «да / скорее да / не знаю / скорее нет / нет». */
export function YesNoQuestion({ question, value, onChange }: YesNoQuestionProps) {
  return (
    <Stack gap="xs">
      <Text fw={500}>{question.title}</Text>
      <SegmentedControl
        aria-label={question.title}
        data={OPTIONS}
        value={typeof value === 'string' ? value : UNKNOWN}
        onChange={onChange}
        fullWidth
        maw={560}
      />
    </Stack>
  );
}
