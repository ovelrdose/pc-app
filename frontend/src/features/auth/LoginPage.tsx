import {
  Button,
  Container,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { notifyError } from '../../lib/notify';
import { zodValidate } from '../../lib/validate';
import { useLogin } from './api';

const schema = z.object({
  email: z.email('Введите корректный email'),
  password: z.string().min(1, 'Введите пароль'),
});

interface LoginFormValues {
  email: string;
  password: string;
}

/** Страница входа: после успеха — на кабинет или туда, откуда пришли. */
export function LoginPage() {
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/cabinet';
  const form = useForm<LoginFormValues>({
    mode: 'controlled',
    initialValues: { email: '', password: '' },
    validate: zodValidate(schema),
  });

  const submit = form.onSubmit(async (values) => {
    try {
      await login.mutateAsync(values);
      navigate(from, { replace: true });
    } catch (error) {
      notifyError(error);
    }
  });

  return (
    <Container size={420} py="xl">
      <Title order={2} mb="md">
        Вход
      </Title>
      <Paper withBorder p="md" component="form" onSubmit={(event) => void submit(event)}>
        <Stack gap="sm">
          <TextInput label="Email" placeholder="you@example.com" {...form.getInputProps('email')} />
          <PasswordInput label="Пароль" {...form.getInputProps('password')} />
          <Button type="submit" loading={login.isPending}>
            Войти
          </Button>
          <Text size="sm" c="dimmed">
            Нет аккаунта? <Link to="/register">Зарегистрироваться</Link> — гостевые сборки
            перенесутся в кабинет.
          </Text>
        </Stack>
      </Paper>
    </Container>
  );
}
