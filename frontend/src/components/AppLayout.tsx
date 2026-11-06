import { AppShell, Container, Group, Text, Title } from '@mantine/core';
import { Link, Outlet } from 'react-router-dom';

import { ColorSchemeToggle } from './ColorSchemeToggle';
import { UserMenu } from '../features/auth/UserMenu';
import classes from './AppLayout.module.css';

export function AppLayout() {
  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between">
            <Link to="/" className={classes.brand}>
              <Title order={3}>Сборщик</Title>
              <Text size="xs" c="dimmed" visibleFrom="xs">
                подбор комплектующих для ПК
              </Text>
            </Link>
            <Group gap="sm">
              <UserMenu />
              <ColorSchemeToggle />
            </Group>
          </Group>
        </Container>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg">
          <Outlet />
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
