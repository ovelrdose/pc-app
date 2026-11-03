import { Badge, Card, Group, List, Progress, Stack, Table, Text, Title } from '@mantine/core';

import { QueryState } from '../../components/QueryState';
import { SCENARIO_TITLES } from '../../lib/labels';
import { useExplanation } from './api';
import { IssuesList } from './IssuesList';

interface ExplanationPanelProps {
  buildId: string;
  expert: boolean;
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'boolean') return value ? 'да' : 'нет';
  return String(value);
}

/** «Почему так»: рассуждение по правилам, вклад задач в полезность, предпочтения, замечания. */
export function ExplanationPanel({ buildId, expert }: ExplanationPanelProps) {
  const explanation = useExplanation(buildId);
  if (!explanation.data) {
    return <QueryState isPending={explanation.isPending} error={explanation.error} />;
  }
  const { reasoning, scenario_contributions, utility, preferences, issues } = explanation.data;
  const scenarios = Object.entries(scenario_contributions)
    .filter(([, value]) => value > 0)
    .sort(([, a], [, b]) => b - a);
  const maxContribution = Math.max(...scenarios.map(([, value]) => value), 1);

  return (
    <Stack gap="lg">
      <Card withBorder>
        <Title order={4} mb="sm">
          Что система поняла о ваших задачах
        </Title>
        {reasoning.length === 0 && <Text c="dimmed">Правила профилирования не сработали.</Text>}
        {expert ? (
          <Table fz="sm" verticalSpacing={6}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Шаг</Table.Th>
                <Table.Th>Правило</Table.Th>
                <Table.Th>CF правила × посылки</Table.Th>
                <Table.Th>Вывод</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {reasoning.map((step) => (
                <Table.Tr key={step.step}>
                  <Table.Td>{step.step}</Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {step.rule_code}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {step.rule_name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {step.rule_cf.toFixed(2)} × {step.premise_cf.toFixed(2)}
                  </Table.Td>
                  <Table.Td>
                    {step.effects.map((effect) => (
                      <Text size="xs" key={`${effect.path}-${effect.outcome}`}>
                        {effect.path} = {formatValue(effect.value)}
                        {effect.cf !== null && ` (CF ${effect.cf.toFixed(2)})`}
                      </Text>
                    ))}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <List type="ordered" spacing={6}>
            {reasoning.map((step) => (
              <List.Item key={step.step}>{step.explanation}</List.Item>
            ))}
          </List>
        )}
      </Card>

      <Card withBorder>
        <Group justify="space-between" mb="sm">
          <Title order={4}>Польза сборки для ваших задач</Title>
          {expert && <Badge variant="light">полезность {utility.toFixed(2)}</Badge>}
        </Group>
        <Stack gap="xs">
          {scenarios.map(([scenario, value]) => (
            <Stack gap={2} key={scenario}>
              <Group justify="space-between">
                <Text size="sm">{SCENARIO_TITLES[scenario] ?? scenario}</Text>
                {expert && (
                  <Text size="xs" c="dimmed">
                    {value.toFixed(2)}
                  </Text>
                )}
              </Group>
              <Progress value={(value / maxContribution) * 100} />
            </Stack>
          ))}
        </Stack>
      </Card>

      {preferences.length > 0 && (
        <Card withBorder>
          <Title order={4} mb="sm">
            Учтённые пожелания
          </Title>
          <List spacing={4} size="sm">
            {preferences.map((preference) => (
              <List.Item key={`${preference.rule_code}-${preference.message}`}>
                {preference.message}
                {expert && (
                  <Text span size="xs" c="dimmed">
                    {' '}
                    ({preference.rule_code}, {preference.delta > 0 ? '+' : ''}
                    {preference.delta})
                  </Text>
                )}
              </List.Item>
            ))}
          </List>
        </Card>
      )}

      <Card withBorder>
        <Title order={4} mb="sm">
          Проверка сборки
        </Title>
        <IssuesList issues={issues} expert={expert} />
      </Card>
    </Stack>
  );
}
