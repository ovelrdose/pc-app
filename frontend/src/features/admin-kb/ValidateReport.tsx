import { Alert, List, Paper, Stack, Text } from '@mantine/core';

import type { ValidateReportOut } from '../../api/types';

/** Отчёт stateless-валидации: ошибки красным, предупреждения жёлтым, golden-итог отдельно. */
export function ValidateReport({ report }: { report: ValidateReportOut }) {
  const goldenTotal = report.golden.passed + report.golden.failed;
  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Text size="sm" fw={500}>
          Отчёт проверки (правил: {report.rules_total}, контрольная сумма:{' '}
          <code>{report.checksum.slice(0, 16)}</code>)
        </Text>

        {report.errors.length > 0 ? (
          <Alert color="red" title={`Ошибки (${report.errors.length}) — публикация заблокирована`}>
            <List size="sm">
              {report.errors.map((error) => (
                <List.Item key={error}>{error}</List.Item>
              ))}
            </List>
          </Alert>
        ) : (
          <Alert color="green">Ошибок нет — черновик может быть опубликован.</Alert>
        )}

        {report.warnings.length > 0 ? (
          <Alert color="yellow" title={`Предупреждения (${report.warnings.length})`}>
            <List size="sm">
              {report.warnings.map((warning) => (
                <List.Item key={warning}>{warning}</List.Item>
              ))}
            </List>
          </Alert>
        ) : null}

        <Text size="sm" fw={500}>
          Эталонные кейсы: {report.golden.passed} из {goldenTotal} прошли
        </Text>
        {report.golden.failed > 0 ? (
          <List size="sm">
            {Object.entries(report.golden.failures).map(([caseId, messages]) => (
              <List.Item key={caseId}>
                <Text size="sm" span fw={500}>
                  {caseId}:
                </Text>{' '}
                {messages.join('; ')}
              </List.Item>
            ))}
          </List>
        ) : null}
      </Stack>
    </Paper>
  );
}
