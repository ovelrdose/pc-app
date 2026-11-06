import { Alert, Button, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { IconArrowLeft, IconInfoCircle, IconTestPipe } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { problemCode } from '../../api/problem';
import { CodeEditor } from '../../components/CodeEditor';
import { QueryState } from '../../components/QueryState';
import { parseYaml } from '../../lib/yaml';
import { useRule, useTestRule } from './api';
import { TestResult } from './TestResult';

const FACTS_TEMPLATE = `# Факты для изолированного прогона: {путь: значение}
# или {путь: {value: значение, cf: 0..1}} (cf по умолчанию 1.0)
user.budget: 90000
user.resolution: "1080p"
`;

/** Тест правила: задаём факты, запускаем изолированный прямой вывод, смотрим результат. */
export function RuleTestPage() {
  const { code } = useParams<{ code: string }>();
  const ruleQuery = useRule(code);
  const testRule = useTestRule(code ?? '');
  const [factsText, setFactsText] = useState(FACTS_TEMPLATE);
  const [parseError, setParseError] = useState<string | null>(null);
  const [goalHint, setGoalHint] = useState<string | null>(null);

  const runTest = () => {
    setGoalHint(null);
    const parsed = parseYaml(factsText);
    if (!parsed.ok) {
      setParseError(parsed.error);
      return;
    }
    if (typeof parsed.value !== 'object' || parsed.value === null || Array.isArray(parsed.value)) {
      setParseError('Факты должны быть объектом вида {путь: значение}');
      return;
    }
    setParseError(null);
    testRule.mutate(
      { facts: parsed.value as Record<string, unknown> },
      {
        onSuccess: () => setGoalHint(null),
        onError: (error) => {
          if (problemCode(error) === 'goal-rule-test-unsupported') {
            setGoalHint(
              'Изолированный прогон неприменим к goal-правилам: подцели требуют обратного вывода с готовой сборкой. Проверяйте такие правила через «Потянет ли?» на странице сборки.',
            );
          }
        },
      },
    );
  };

  const rule = ruleQuery.data?.rule;

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Title order={3}>Проверка правила {code}</Title>
          <Text size="sm" c="dimmed">
            {rule
              ? `${rule.name} · вид «${rule.kind}»`
              : 'Изолированный прямой вывод на заданных фактах'}
          </Text>
        </div>
        <Button
          component={Link}
          to={`/admin/kb/rules/${code}`}
          variant="default"
          leftSection={<IconArrowLeft size={16} />}
        >
          В редактор
        </Button>
      </Group>

      <QueryState isPending={ruleQuery.isPending} error={ruleQuery.error} />

      {rule?.kind === 'goal' ? (
        <Alert color="violet" icon={<IconInfoCircle size={16} />} title="Goal-правило">
          Для целей обратного вывода изолированный прогон не поддерживается: сервер вернёт ошибку.
          Такие правила проверяются на готовой сборке в блоке «Потянет ли?».
        </Alert>
      ) : null}

      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          <Text size="sm" fw={500}>
            Входные факты
          </Text>
          <Text size="xs" c="dimmed">
            Формат: <code>{'{путь: значение}'}</code> или{' '}
            <code>{'{путь: {value: значение, cf: 0..1}}'}</code>. Факт виден условию, только если
            его cf ≥ 0.2. Можно писать и в JSON, и в YAML.
          </Text>
          <CodeEditor
            ariaLabel="Входные факты"
            language="yaml"
            value={factsText}
            onChange={setFactsText}
            height={220}
          />
          <Group>
            <Button
              leftSection={<IconTestPipe size={16} />}
              loading={testRule.isPending}
              onClick={runTest}
            >
              Запустить
            </Button>
          </Group>
        </Stack>
      </Paper>

      {parseError ? (
        <Alert color="red" title="Факты не разобраны">
          {parseError}
        </Alert>
      ) : null}
      {testRule.error && problemCode(testRule.error) !== 'goal-rule-test-unsupported' ? (
        <Alert color="red" title="Прогон не выполнен">
          {testRule.error instanceof Error ? testRule.error.message : 'Ошибка сервера'}
        </Alert>
      ) : null}
      {goalHint ? (
        <Alert color="violet" icon={<IconInfoCircle size={16} />} title="Прогон неприменим">
          {goalHint}
        </Alert>
      ) : null}

      {testRule.data ? <TestResult result={testRule.data} /> : null}
    </Stack>
  );
}
