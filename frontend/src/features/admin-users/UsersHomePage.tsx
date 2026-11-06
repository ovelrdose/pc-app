import { Button, Group, Modal, Pagination, Select, Text, TextInput, Title } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import type { UserAdminOut, UserRole } from '../../api/types';
import { useMe } from '../auth/api';
import { PAGE_SIZE, usePatchUser, useUsers, type UserFilters } from '../admin-kb/api';
import { USER_ROLE_TITLES } from '../admin-kb/labels';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { UsersTable } from './UsersTable';

/** Управление пользователями (superadmin): роли, блокировка с отзывом сессий. */
export function UsersHomePage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [role, setRole] = useState<UserRole | null>(null);
  const [q, setQ] = useState('');
  const [isActive, setIsActive] = useState<boolean | null>(null);
  const [page, setPage] = useState(1);
  const [blockTarget, setBlockTarget] = useState<UserAdminOut | null>(null);

  const filters: UserFilters = { role, q, isActive, page };
  const users = useUsers(filters);
  const patch = usePatchUser();

  const items = users.data?.items ?? [];
  const total = users.data?.total ?? 0;

  /** После ошибки (409 self-change/last-superadmin) откатываем локальное состояние строки. */
  const revert = () => {
    void queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
  };

  const changeRole = (user: UserAdminOut, nextRole: UserRole) => {
    patch.mutate(
      { id: user.id, patch: { role: nextRole } },
      {
        onError: (error) => {
          notifyError(error);
          revert();
        },
      },
    );
  };

  const confirmBlock = () => {
    if (!blockTarget) return;
    patch.mutate(
      { id: blockTarget.id, patch: { is_active: false } },
      {
        onSuccess: () => setBlockTarget(null),
        onError: (error) => {
          notifyError(error);
          revert();
          setBlockTarget(null);
        },
      },
    );
  };

  const toggleActive = (user: UserAdminOut, next: boolean) => {
    if (!next) {
      // Блокировка требует подтверждения: отзывает все сессии пользователя.
      setBlockTarget(user);
      return;
    }
    patch.mutate(
      { id: user.id, patch: { is_active: true } },
      {
        onError: (error) => {
          notifyError(error);
          revert();
        },
      },
    );
  };

  return (
    <>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={3}>Пользователи</Title>
          <Text size="sm" c="dimmed">
            {total > 0 ? `Пользователей: ${total}` : 'Учётные записи'}
          </Text>
        </div>
      </Group>

      <Group mt="md" gap="sm" wrap="wrap" align="flex-end">
        <Select
          label="Роль"
          placeholder="Все"
          clearable
          w={190}
          data={(Object.keys(USER_ROLE_TITLES) as UserRole[]).map((value) => ({
            value,
            label: USER_ROLE_TITLES[value],
          }))}
          value={role}
          onChange={(value) => {
            setRole((value as UserRole | null) ?? null);
            setPage(1);
          }}
        />
        <Select
          label="Статус"
          placeholder="Все"
          clearable
          w={160}
          data={[
            { value: 'true', label: 'Активные' },
            { value: 'false', label: 'Заблокированные' },
          ]}
          value={isActive === null ? null : String(isActive)}
          onChange={(value) => {
            setIsActive(value === null ? null : value === 'true');
            setPage(1);
          }}
        />
        <TextInput
          label="Поиск"
          placeholder="email"
          w={240}
          leftSection={<IconSearch size={16} />}
          value={q}
          onChange={(event) => {
            setQ(event.currentTarget.value);
            setPage(1);
          }}
        />
      </Group>

      <QueryState isPending={users.isPending} error={users.error} />
      {!users.isPending && !users.error && items.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          По заданным фильтрам пользователей не найдено.
        </Text>
      ) : null}
      {items.length > 0 ? (
        <>
          <UsersTable
            items={items}
            currentUserId={me.data?.id ?? null}
            busy={patch.isPending}
            onChangeRole={changeRole}
            onToggleActive={toggleActive}
          />
          <Group justify="center" mt="md">
            <Pagination
              total={Math.max(1, Math.ceil(total / PAGE_SIZE))}
              value={page}
              onChange={setPage}
            />
          </Group>
        </>
      ) : null}

      <Modal
        opened={blockTarget !== null}
        onClose={() => setBlockTarget(null)}
        title={`Заблокировать ${blockTarget?.email ?? ''}?`}
      >
        <Text size="sm">
          Пользователь потеряет доступ: все его refresh-токены будут отозваны и действующие сессии
          завершатся. Разблокировать можно будет переключателем «Активен».
        </Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setBlockTarget(null)}>
            Отмена
          </Button>
          <Button color="red" loading={patch.isPending} onClick={confirmBlock}>
            Заблокировать
          </Button>
        </Group>
      </Modal>
    </>
  );
}
