import { Button, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <Stack align="center" py="xl">
      <Title order={2}>Страница не найдена</Title>
      <Text c="dimmed">Проверьте адрес или вернитесь на главную.</Text>
      <Button component={Link} to="/">
        На главную
      </Button>
    </Stack>
  );
}
