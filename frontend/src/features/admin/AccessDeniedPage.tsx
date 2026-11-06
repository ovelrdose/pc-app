import { Anchor, Center, Stack, Text, Title } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { Link } from 'react-router-dom';

/** Экран 403: вошёл, но роли не хватает для раздела админки. */
export function AccessDeniedPage() {
  return (
    <Center py="xl">
      <Stack align="center" gap="xs" maw={440}>
        <IconLock size={40} stroke={1.5} />
        <Title order={3}>Нет доступа к разделу</Title>
        <Text c="dimmed" ta="center">
          Этот раздел админки доступен другой роли. Если доступ нужен, попросите суперадминистратора
          изменить вашу роль.
        </Text>
        <Anchor component={Link} to="/">
          На главную
        </Anchor>
      </Stack>
    </Center>
  );
}
