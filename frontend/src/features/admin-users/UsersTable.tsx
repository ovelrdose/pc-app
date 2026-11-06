import { Select, Switch, Table, Text } from '@mantine/core';

import type { UserAdminOut, UserRole } from '../../api/types';
import { formatDateTime } from '../../lib/format';
import { USER_ROLE_TITLES } from '../admin-kb/labels';

interface UsersTableProps {
  items: UserAdminOut[];
  /** id текущего суперадмина — свою строку нельзя править. */
  currentUserId: string | null;
  busy: boolean;
  onChangeRole: (user: UserAdminOut, role: UserRole) => void;
  onToggleActive: (user: UserAdminOut, isActive: boolean) => void;
}

const ROLE_OPTIONS = (Object.keys(USER_ROLE_TITLES) as UserRole[]).map((value) => ({
  value,
  label: USER_ROLE_TITLES[value],
}));

/** Таблица пользователей: email, роль (Select), блокировка (Switch), дата создания. */
export function UsersTable({
  items,
  currentUserId,
  busy,
  onChangeRole,
  onToggleActive,
}: UsersTableProps) {
  return (
    <Table striped highlightOnHover verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Email</Table.Th>
          <Table.Th>Роль</Table.Th>
          <Table.Th>Активен</Table.Th>
          <Table.Th>Зарегистрирован</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((user) => {
          const isSelf = user.id === currentUserId;
          return (
            <Table.Tr key={user.id}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {user.email}
                </Text>
                {isSelf ? (
                  <Text size="xs" c="dimmed">
                    это вы — свою роль и блокировку менять нельзя
                  </Text>
                ) : null}
              </Table.Td>
              <Table.Td>
                <Select
                  aria-label={`Роль: ${user.email}`}
                  w={200}
                  data={ROLE_OPTIONS}
                  value={user.role}
                  disabled={busy || isSelf}
                  onChange={(next) => next && onChangeRole(user, next as UserRole)}
                  allowDeselect={false}
                />
              </Table.Td>
              <Table.Td>
                <Switch
                  aria-label={`Активен: ${user.email}`}
                  checked={user.is_active}
                  disabled={busy || isSelf}
                  onChange={(event) => onToggleActive(user, event.currentTarget.checked)}
                />
              </Table.Td>
              <Table.Td>
                <Text size="sm">{formatDateTime(user.created_at)}</Text>
              </Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
