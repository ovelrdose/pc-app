import { NumberInput } from '@mantine/core';

import type { QuestionOut } from '../../api/types';
import { formatRubles } from '../../lib/format';

interface NumberQuestionProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: number | null) => void;
}

/** Числовой вопрос (бюджет). */
export function NumberQuestion({ question, value, onChange }: NumberQuestionProps) {
  const min = question.min ?? 0;
  const max = question.max ?? undefined;
  return (
    <NumberInput
      label={question.title}
      description={
        max === undefined
          ? `От ${formatRubles(min)}`
          : `От ${formatRubles(min)} до ${formatRubles(max)}`
      }
      size="md"
      maw={320}
      min={min}
      max={max}
      step={question.step ?? 1}
      thousandSeparator=" "
      allowDecimal={false}
      allowNegative={false}
      value={typeof value === 'number' ? value : ''}
      onChange={(next) => onChange(typeof next === 'number' ? next : null)}
    />
  );
}
