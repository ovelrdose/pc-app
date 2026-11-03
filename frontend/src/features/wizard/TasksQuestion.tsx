import { Chip, Group, Stack, Text } from '@mantine/core';

import type { QuestionOut } from '../../api/types';
import { asTasks, type TasksAnswer } from './answers';

interface TasksQuestionProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: TasksAnswer) => void;
}

/** Основная задача (одна) и дополнительные (несколько, без основной). */
export function TasksQuestion({ question, value, onChange }: TasksQuestionProps) {
  const { main, extra } = asTasks(value);
  const options = question.options.map((option) => ({
    key: String(option.value),
    label: option.label,
  }));

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Text fw={500}>{question.title}</Text>
        <Chip.Group
          multiple={false}
          value={main ?? ''}
          onChange={(key) => onChange({ main: key, extra: extra.filter((e) => e !== key) })}
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
      {main !== null && (
        <Stack gap="xs">
          <Text fw={500}>{question.extra_title}</Text>
          <Text size="sm" c="dimmed">
            Можно пропустить. Дополнительные задачи учитываются слабее основной.
          </Text>
          <Chip.Group multiple value={extra} onChange={(keys) => onChange({ main, extra: keys })}>
            <Group gap="xs">
              {options
                .filter((option) => option.key !== main)
                .map((option) => (
                  <Chip key={option.key} value={option.key} variant="outline">
                    {option.label}
                  </Chip>
                ))}
            </Group>
          </Chip.Group>
        </Stack>
      )}
    </Stack>
  );
}
