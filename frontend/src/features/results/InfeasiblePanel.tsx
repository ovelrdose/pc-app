import { Alert, Button, Card, Group, List, Stack, Table, Text, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';

import type { ConsultationOut } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { formatNumber, formatRub, formatRubles } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';
import { notifyError } from '../../lib/notify';
import { useStartConsultation } from '../wizard/api';
import type { Answers } from '../wizard/answers';
import { useInfeasible } from './api';
import { CompromiseCard } from './CompromiseCard';

const BUDGET_STEP = 1000;

/** Бюджет, округлённый вверх до тысячи рублей. */
function roundBudget(rub: number): number {
  return Math.ceil(rub / BUDGET_STEP) * BUDGET_STEP;
}

interface InfeasiblePanelProps {
  consultation: ConsultationOut;
}

/** «Подобрать не удалось»: что мешает, как ослабить требования, что можно собрать. */
export function InfeasiblePanel({ consultation }: InfeasiblePanelProps) {
  const navigate = useNavigate();
  const start = useStartConsultation();
  const report = useInfeasible(consultation.id, true);
  const brief = consultation.infeasibility;
  const owned = consultation.owned.map((item) => item.component_id);
  const alreadyWaived = consultation.waived.map((item) => item.fact);

  /** Новая консультация с изменёнными ответами; прежние уступки сохраняются. */
  const retry = (patch: Answers, waived: string[] = []) => {
    const answers: Answers = { ...consultation.answers, ...patch };
    start.mutate(
      {
        answers,
        ownedComponentIds: owned,
        waived: [...new Set([...alreadyWaived, ...waived])],
      },
      {
        onSuccess: (next) => navigate(`/consultations/${next.id}`),
        onError: notifyError,
      },
    );
  };

  /** Ослабление плюс бюджет не ниже минимально нужного. */
  const withBudget = (patch: Answers, minimumRub: number): Answers => {
    const budget =
      typeof consultation.answers.budget === 'number' ? consultation.answers.budget : 0;
    return { ...patch, budget: Math.max(budget, roundBudget(minimumRub)) };
  };

  return (
    <Stack gap="lg">
      <Alert color="orange" icon={<IconAlertTriangle />} title="Подобрать сборку не удалось">
        {brief?.reason}
        {brief && brief.empty_categories.length > 0 && (
          <Text size="sm" mt="xs">
            Нет подходящих товаров:{' '}
            {brief.empty_categories.map((category) => CATEGORY_TITLES[category]).join(', ')}.
          </Text>
        )}
      </Alert>

      <QueryState isPending={report.isPending} error={report.error} />
      {report.data && (
        <>
          <Card withBorder>
            <Stack gap="xs">
              <Title order={4}>Бюджет</Title>
              <Text>
                Ваш бюджет: {formatRubles(report.data.budget_rub)}.{' '}
                {report.data.min_budget_rub !== null
                  ? `Самая дешёвая подходящая сборка стоит от ${formatRubles(report.data.min_budget_rub)}.`
                  : 'Под эти требования в каталоге нет совместимого набора деталей.'}
              </Text>
              {report.data.min_budget_rub !== null && (
                <Button
                  w="fit-content"
                  loading={start.isPending}
                  onClick={() => retry(withBudget({}, report.data.min_budget_rub ?? 0))}
                >
                  Подобрать с бюджетом {formatRubles(roundBudget(report.data.min_budget_rub))}
                </Button>
              )}
            </Stack>
          </Card>

          {report.data.compromise && (
            <CompromiseCard
              compromise={report.data.compromise}
              loading={start.isPending}
              onAccept={() =>
                retry(report.data.compromise?.answers ?? {}, report.data.compromise?.waived)
              }
            />
          )}

          {report.data.blocking.length > 0 && (
            <Card withBorder>
              <Title order={4} mb="xs">
                Что сильнее всего поднимает цену
              </Title>
              <List spacing="xs">
                {report.data.blocking.map((item) => (
                  <List.Item key={item.fact}>
                    {item.title}
                    {typeof item.value === 'number' && `: от ${formatNumber(item.value)}`}
                    {item.min_budget_without_rub !== null &&
                      ` — без этого требования хватит ${formatRubles(item.min_budget_without_rub)}`}
                    {item.rules.length > 0 && (
                      <Text span size="xs" c="dimmed">
                        {' '}
                        (правила {item.rules.join(', ')})
                      </Text>
                    )}
                  </List.Item>
                ))}
              </List>
            </Card>
          )}

          {report.data.relaxations.length > 0 && (
            <Card withBorder>
              <Title order={4} mb="xs">
                Как ослабить требования
              </Title>
              <Table>
                <Table.Tbody>
                  {report.data.relaxations.map((relaxation) => (
                    <Table.Tr key={relaxation.title}>
                      <Table.Td>{relaxation.title}</Table.Td>
                      <Table.Td>от {formatRubles(relaxation.min_budget_rub)}</Table.Td>
                      <Table.Td ta="right">
                        <Button
                          size="xs"
                          variant="light"
                          loading={start.isPending}
                          onClick={() =>
                            retry(withBudget(relaxation.answers, relaxation.min_budget_rub))
                          }
                        >
                          Подобрать с этим
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
          )}

          {report.data.best_effort && (
            <Card withBorder>
              <Group justify="space-between" mb="xs">
                <Title order={4}>Что можно собрать, если отказаться от части требований</Title>
                <Text fw={600}>{formatRub(report.data.best_effort.total_price_kop)}</Text>
              </Group>
              <Table fz="sm">
                <Table.Tbody>
                  {report.data.best_effort.items.map((item) => (
                    <Table.Tr key={item.category}>
                      <Table.Td c="dimmed">{CATEGORY_TITLES[item.category]}</Table.Td>
                      <Table.Td>{item.name}</Table.Td>
                      <Table.Td ta="right">{formatRub(item.price_kop)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {report.data.best_effort.unmet.length > 0 && (
                <Text size="sm" mt="xs" c="dimmed">
                  Не выполнено: {report.data.best_effort.unmet.join('; ')}
                </Text>
              )}
            </Card>
          )}
        </>
      )}
    </Stack>
  );
}
