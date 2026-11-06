import { Button, Menu } from '@mantine/core';
import { IconChevronDown, IconDoorExit, IconSettings, IconUserCircle } from '@tabler/icons-react';
import { Link, useLocation } from 'react-router-dom';

import { useLogout, useMe } from './api';
import { ADMIN_ROLES } from '../admin/roles';

/** Кнопка входа или меню аккаунта в шапке. */
export function UserMenu() {
  const me = useMe();
  const logout = useLogout();
  const location = useLocation();

  if (me.isLoading) return null;
  if (!me.data) {
    return (
      <Button
        component={Link}
        to="/login"
        state={{ from: location.pathname + location.search }}
        variant="default"
        size="compact-md"
        leftSection={<IconUserCircle size={16} />}
      >
        Войти
      </Button>
    );
  }
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <Button variant="default" size="compact-md" rightSection={<IconChevronDown size={14} />}>
          {me.data.email}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={Link} to="/cabinet" leftSection={<IconUserCircle size={16} />}>
          Личный кабинет
        </Menu.Item>
        {ADMIN_ROLES.includes(me.data.role) ? (
          <Menu.Item component={Link} to="/admin" leftSection={<IconSettings size={16} />}>
            Админка
          </Menu.Item>
        ) : null}
        <Menu.Item
          color="red"
          leftSection={<IconDoorExit size={16} />}
          onClick={() => logout.mutate()}
        >
          Выйти
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
