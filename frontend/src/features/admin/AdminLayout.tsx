import { Button, Group, Stack, Title } from '@mantine/core';
import { Link, Outlet, useLocation } from 'react-router-dom';

import { useMe } from '../auth/api';
import { sectionsForRole } from './roles';

/** Активный раздел: самый длинный путь, являющийся префиксом текущего маршрута. */
function activeSection(pathname: string, paths: string[]): string {
  return (
    paths
      .filter((path) => pathname === path || pathname.startsWith(`${path}/`))
      .sort((a, b) => b.length - a.length)[0] ?? ''
  );
}

/** Общий каркас админки: заголовок и навигация по доступным роли разделам. */
export function AdminLayout() {
  const me = useMe();
  const location = useLocation();
  const sections = me.data ? sectionsForRole(me.data.role) : [];
  const active = activeSection(
    location.pathname,
    sections.map((section) => section.path),
  );

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Title order={2}>Администрирование</Title>
      </Group>
      <Group gap="xs">
        {sections.map((section) => (
          <Button
            key={section.path}
            component={Link}
            to={section.path}
            size="compact-md"
            variant={active === section.path ? 'filled' : 'default'}
          >
            {section.title}
          </Button>
        ))}
      </Group>
      <Outlet />
    </Stack>
  );
}
