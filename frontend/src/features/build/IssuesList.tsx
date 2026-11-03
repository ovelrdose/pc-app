import { Alert, Stack, Text } from '@mantine/core';
import { IconAlertTriangle, IconBulb, IconCircleX } from '@tabler/icons-react';

import type { IssueOut } from '../../api/types';

interface IssueStyle {
  color: string;
  title: string;
  icon: typeof IconBulb;
}

const SUGGEST: IssueStyle = { color: 'blue', title: 'Совет', icon: IconBulb };

const STYLES: Record<string, IssueStyle> = {
  reject: { color: 'red', title: 'Ошибка совместимости', icon: IconCircleX },
  warn: { color: 'orange', title: 'Предупреждение', icon: IconAlertTriangle },
  suggest: SUGGEST,
};

interface IssuesListProps {
  issues: IssueOut[];
  expert: boolean;
}

/** Замечания проверки сборки: ошибки, предупреждения, советы. */
export function IssuesList({ issues, expert }: IssuesListProps) {
  if (issues.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Замечаний нет: все детали совместимы.
      </Text>
    );
  }
  return (
    <Stack gap="xs">
      {issues.map((issue) => {
        const style = STYLES[issue.action] ?? SUGGEST;
        const Icon = style.icon;
        return (
          <Alert
            key={`${issue.rule_code}-${issue.message}`}
            color={style.color}
            icon={<Icon size={18} />}
            title={expert ? `${style.title} · ${issue.rule_code}` : style.title}
            p="xs"
          >
            {issue.message}
          </Alert>
        );
      })}
    </Stack>
  );
}
