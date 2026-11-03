import { Card, Group, Stack, Switch, Tabs, Title } from '@mantine/core';
import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';

import { QueryState } from '../../components/QueryState';
import { useBuild } from './api';
import { BuildHeader } from './BuildHeader';
import { ChangeSummary } from './ChangeSummary';
import { ComponentList } from './ComponentList';
import { ExplanationPanel } from './ExplanationPanel';
import { HypothesisPanel } from './HypothesisPanel';
import { IssuesList } from './IssuesList';
import { PerformancePanel } from './PerformancePanel';
import { RedistributeButton } from './RedistributeButton';
import type { EditNavigationState } from './useApplyEdit';
import { WhyNotPanel } from './WhyNotPanel';

function isEditState(state: unknown): state is EditNavigationState {
  return typeof state === 'object' && state !== null && 'modification' in state;
}

/** Страница сборки: состав и правки, прогноз, объяснение, гипотезы. */
export function BuildPage() {
  const { id } = useParams();
  const location = useLocation();
  const build = useBuild(id);
  const [expert, setExpert] = useState(false);

  if (!build.data) return <QueryState isPending={build.isPending} error={build.error} />;
  const data = build.data;
  const state: unknown = location.state;
  const modification =
    isEditState(state) && state.modification.build.id === data.id ? state.modification : null;

  return (
    <Stack gap="lg" py="md">
      <BuildHeader key={data.id} build={data} />
      {modification && <ChangeSummary modification={modification} />}

      <Tabs defaultValue="parts" keepMounted={false}>
        <Group justify="space-between">
          <Tabs.List>
            <Tabs.Tab value="parts">Состав</Tabs.Tab>
            <Tabs.Tab value="performance">Производительность</Tabs.Tab>
            <Tabs.Tab value="why">Почему так</Tabs.Tab>
            <Tabs.Tab value="hypotheses">Потянет ли?</Tabs.Tab>
          </Tabs.List>
          <Switch
            label="Экспертный режим"
            checked={expert}
            onChange={(event) => setExpert(event.currentTarget.checked)}
          />
        </Group>

        <Tabs.Panel value="parts" pt="md">
          <Stack gap="lg">
            <Card withBorder>
              <Group justify="space-between" mb="sm">
                <Title order={4}>Состав</Title>
                <RedistributeButton buildId={data.id} items={data.items} />
              </Group>
              <ComponentList buildId={data.id} items={data.items} />
            </Card>
            <Card withBorder>
              <Title order={4} mb="sm">
                Замечания
              </Title>
              <IssuesList issues={data.issues} expert={expert} />
            </Card>
            <WhyNotPanel buildId={data.id} expert={expert} />
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="performance" pt="md">
          <PerformancePanel performance={data.performance} />
        </Tabs.Panel>
        <Tabs.Panel value="why" pt="md">
          <ExplanationPanel buildId={data.id} expert={expert} />
        </Tabs.Panel>
        <Tabs.Panel value="hypotheses" pt="md">
          <HypothesisPanel buildId={data.id} expert={expert} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
