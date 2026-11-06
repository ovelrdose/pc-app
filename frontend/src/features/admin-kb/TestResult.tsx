import { Alert, Badge, Group, Paper, Stack, Table, Text } from '@mantine/core';

import type { RuleTestOut } from '../../api/types';

/** Результат прогона: срабатывание, CF посылки, действия, факты после, ошибки вычисления. */
export function TestResult({ result }: { result: RuleTestOut }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group gap="md">
          <Text size="sm" fw={500}>
            Результат прогона
          </Text>
          {result.matched ? (
            <Badge color="green">Сработало</Badge>
          ) : (
            <Badge color="gray">Не сработало</Badge>
          )}
          {result.premise_cf !== null ? (
            <Text size="sm">
              CF посылки: <b>{result.premise_cf.toFixed(2)}</b>
            </Text>
          ) : null}
        </Group>

        {result.actions.length > 0 ? (
          <div>
            <Text size="sm" fw={500} mb={4}>
              Действия ({result.actions.length})
            </Text>
            <Table striped withTableBorder verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Действие</Table.Th>
                  <Table.Th>Детали</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.actions.map((action, index) => (
                  <Table.Tr key={index}>
                    <Table.Td>
                      <Badge variant="light">{action.action}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {action.fact ? <code>{action.fact}</code> : null}
                        {action.value !== undefined && action.value !== null
                          ? ` = ${JSON.stringify(action.value)}`
                          : null}
                        {action.weight !== null && action.weight !== undefined
                          ? ` (вес ${action.weight})`
                          : null}
                        {action.message ? ` — ${action.message}` : ''}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
        ) : (
          <Text size="sm" c="dimmed">
            Действий нет.
          </Text>
        )}

        {result.facts_after.length > 0 ? (
          <div>
            <Text size="sm" fw={500} mb={4}>
              Факты после прогона
            </Text>
            <Table striped withTableBorder verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Путь</Table.Th>
                  <Table.Th>Значение</Table.Th>
                  <Table.Th>CF</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.facts_after.map((fact) => (
                  <Table.Tr key={fact.path}>
                    <Table.Td>
                      <code>{fact.path}</code>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{JSON.stringify(fact.value)}</Text>
                    </Table.Td>
                    <Table.Td>{fact.cf.toFixed(2)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
        ) : null}

        {result.failures.length > 0 ? (
          <Alert color="yellow" title="Ошибки вычисления (rule_failed)">
            {result.failures.map((failure) => (
              <Text size="sm" key={failure}>
                • {failure}
              </Text>
            ))}
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}
