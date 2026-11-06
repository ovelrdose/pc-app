import { Card, Grid, Group, Text, Title } from '@mantine/core';
import { IconArrowRight } from '@tabler/icons-react';
import { Link, Navigate } from 'react-router-dom';

import { useMe } from '../auth/api';
import { homeSectionPath, sectionsForRole } from './roles';

/**
 * Обзорная страница `/admin`: карточки доступных роли разделов.
 * Если доступен ровно один раздел — сразу ведём туда (ADR 0010, п. 10).
 */
export function AdminHomePage() {
  const me = useMe();
  if (!me.data) return null;
  const sections = sectionsForRole(me.data.role);
  if (sections.length === 1) {
    return <Navigate to={homeSectionPath(me.data.role)} replace />;
  }
  return (
    <Grid>
      {sections.map((section) => (
        <Grid.Col key={section.path} span={{ base: 12, sm: 6 }}>
          <Card component={Link} to={section.path} withBorder padding="lg" radius="md" h="100%">
            <Group justify="space-between" wrap="nowrap">
              <div>
                <Title order={4}>{section.title}</Title>
                <Text size="xs" c="dimmed" mt={2}>
                  {section.audience}
                </Text>
                <Text size="sm" c="dimmed" mt="xs">
                  {section.description}
                </Text>
              </div>
              <IconArrowRight size={20} stroke={1.5} />
            </Group>
          </Card>
        </Grid.Col>
      ))}
    </Grid>
  );
}
