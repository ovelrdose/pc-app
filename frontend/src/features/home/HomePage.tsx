import { Button, List, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';

import { ApiStatusBadge } from './ApiStatusBadge';

const capabilities = [
  'подберёт три варианта сборки под ваши задачи и бюджет',
  'проверит совместимость всех деталей',
  'оценит производительность в играх и программах',
  'объяснит, почему выбрана каждая деталь',
];

export function HomePage() {
  return (
    <Stack gap="lg" py="xl" maw={720}>
      <ApiStatusBadge />
      <Title order={1}>Соберём компьютер под ваши задачи</Title>
      <Text size="lg">Экспертная система магазина «Сборщик»:</Text>
      <List spacing="xs">
        {capabilities.map((item) => (
          <List.Item key={item}>{item}</List.Item>
        ))}
      </List>
      <Button component={Link} to="/wizard" size="lg" w="fit-content">
        Подобрать ПК
      </Button>
    </Stack>
  );
}
