import { Alert, Button, Card, Group, Select, Stack, Text, Title } from '@mantine/core';
import { useState } from 'react';

import type { GoalOut, HypothesisOut } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { notifyError } from '../../lib/notify';
import { useGoals, useHypothesis } from './api';
import { ProofTree } from './ProofTree';

type Binding = string | number;

const VERDICTS: Record<HypothesisOut['status'], { color: string; title: string }> = {
  proved: { color: 'teal', title: 'Да, потянет' },
  failed: { color: 'red', title: 'Нет, не потянет' },
  unknown: { color: 'gray', title: 'Нужно уточнить' },
};

interface HypothesisPanelProps {
  buildId: string;
  expert: boolean;
}

function goalKey(goal: GoalOut): string {
  return `${goal.predicate}:${JSON.stringify(goal.args)}`;
}

/** «Потянет ли?»: проверка цели обратным выводом с уточняющими вопросами. */
export function HypothesisPanel({ buildId, expert }: HypothesisPanelProps) {
  const goals = useGoals();
  const check = useHypothesis(buildId);
  const [selected, setSelected] = useState<string | null>(null);
  const [bindings, setBindings] = useState<Record<string, Binding>>({});

  const goal = goals.data?.find((item) => goalKey(item) === selected);
  const result = check.data;

  const run = (nextBindings: Record<string, Binding>) => {
    if (!goal) return;
    check.mutate(
      { predicate: goal.predicate, args: goal.args, bindings: nextBindings },
      { onError: notifyError },
    );
  };

  if (!goals.data) return <QueryState isPending={goals.isPending} error={goals.error} />;

  return (
    <Stack gap="lg">
      <Card withBorder>
        <Stack gap="sm">
          <Title order={4}>Потянет ли эта сборка?</Title>
          <Group align="flex-end">
            <Select
              label="Что проверить"
              placeholder="Например, Cyberpunk 2077 на ультра"
              data={goals.data.map((item) => ({ value: goalKey(item), label: item.title }))}
              value={selected}
              onChange={(value) => {
                setSelected(value);
                setBindings({});
                check.reset();
              }}
              searchable
              nothingFoundMessage="Ничего не найдено"
              w={420}
            />
            <Button disabled={!goal} loading={check.isPending} onClick={() => run(bindings)}>
              Проверить
            </Button>
          </Group>
        </Stack>
      </Card>

      {result && (
        <Card withBorder>
          <Stack gap="md">
            <Alert color={VERDICTS[result.status].color} title={VERDICTS[result.status].title}>
              {result.status === 'unknown' && result.questions.length > 0
                ? 'Ответьте на вопросы ниже — проверка продолжится.'
                : result.tree.label}
            </Alert>
            {result.questions.map((question) => (
              <Select
                key={question.variable}
                label={question.question}
                data={question.options.map((option) => String(option))}
                value={
                  bindings[question.variable] !== undefined
                    ? String(bindings[question.variable])
                    : null
                }
                onChange={(value) => {
                  const option = question.options.find((item) => String(item) === value);
                  if (option === undefined || typeof option === 'boolean') return;
                  setBindings((prev) => ({ ...prev, [question.variable]: option }));
                }}
                w={260}
              />
            ))}
            {result.questions.length > 0 && (
              <Button
                w="fit-content"
                loading={check.isPending}
                disabled={result.questions.some((q) => bindings[q.variable] === undefined)}
                onClick={() => run(bindings)}
              >
                Ответить и проверить
              </Button>
            )}
            <div>
              <Text fw={500} mb="xs">
                Ход доказательства
              </Text>
              <ProofTree node={result.tree} expert={expert} />
            </div>
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
