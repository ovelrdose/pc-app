import { Anchor, Button, Card, Container, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';

import { formatDateTime, formatRub } from '../../lib/format';
import { useMe, useSavedBuilds } from '../auth/api';

/** Личный кабинет: сохранённые сборки текущего аккаунта. */
export function CabinetPage() {
  const me = useMe();
  const saved = useSavedBuilds(Boolean(me.data));

  if (me.isLoading) {
    return (
      <Container py="xl">
        <Loader />
      </Container>
    );
  }
  if (!me.data) {
    return (
      <Container size={520} py="xl">
        <Title order={2} mb="md">
          Личный кабинет
        </Title>
        <Text c="dimmed" mb="md">
          Кабинет доступен после входа. Сохранённые гостевые сборки перенесутся в аккаунт
          автоматически.
        </Text>
        <Button component={Link} to="/login" state={{ from: '/cabinet' }}>
          Войти
        </Button>
      </Container>
    );
  }

  return (
    <Container size="lg" py="xl">
      <Title order={2} mb="md">
        Сохранённые сборки
      </Title>
      {saved.isLoading ? (
        <Loader />
      ) : saved.data && saved.data.builds.length > 0 ? (
        <Stack gap="sm">
          {saved.data.builds.map(({ consultation_id, build }) => (
            <Card key={build.id} withBorder p="sm">
              <Group justify="space-between" wrap="wrap">
                <div>
                  <Anchor component={Link} to={`/builds/${build.id}`} fw={600}>
                    {build.title ?? `Сборка от ${formatDateTime(build.created_at)}`}
                  </Anchor>
                  <Text size="sm" c="dimmed">
                    {build.items.length} деталей · полезность {build.utility}
                  </Text>
                </div>
                <Group gap="md">
                  <Text fw={600}>{formatRub(build.total_price_kop)}</Text>
                  <Anchor component={Link} to={`/consultations/${consultation_id}`} size="sm">
                    Консультация
                  </Anchor>
                </Group>
              </Group>
            </Card>
          ))}
        </Stack>
      ) : (
        <Text c="dimmed">
          Пока пусто. Откройте подобранную сборку и нажмите «Сохранить» — она появится здесь.
        </Text>
      )}
    </Container>
  );
}
