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
import { useRegister } from './api';

const schema = z
  .object({
    email: z.email('Введите корректный email'),
    password: z.string().min(8, 'Минимум 8 символов'),
    confirm: z.string().min(1, 'Повторите пароль'),
  })
  .refine((values) => values.password === values.confirm, {
    path: ['confirm'],
    message: 'Пароли не совпадают',
  });

interface RegisterFormValues {
  email: string;
  password: string;
  confirm: string;
}

/** Страница регистрации: по успеху гостевые сборки переносятся в новый аккаунт. */
export function RegisterPage() {
  const register = useRegister();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/cabinet';
  const form = useForm<RegisterFormValues>({
    mode: 'controlled',
    initialValues: { email: '', password: '', confirm: '' },
    validate: zodValidate(schema),
  });

  const submit = form.onSubmit(async ({ email, password }) => {
    try {
      await register.mutateAsync({ email, password });
      navigate(from, { replace: true });
    } catch (error) {
      notifyError(error);
    }
  });

  return (
    <Container size={420} py="xl">
      <Title order={2} mb="md">
        Регистрация
      </Title>
      <Paper withBorder p="md" component="form" onSubmit={(event) => void submit(event)}>
        <Stack gap="sm">
          <TextInput label="Email" placeholder="you@example.com" {...form.getInputProps('email')} />
          <PasswordInput
            label="Пароль"
            description="Минимум 8 символов"
            {...form.getInputProps('password')}
          />
          <PasswordInput label="Повторите пароль" {...form.getInputProps('confirm')} />
          <Button type="submit" loading={register.isPending}>
            Создать аккаунт
          </Button>
          <Text size="sm" c="dimmed">
            Уже есть аккаунт? <Link to="/login">Войти</Link>
          </Text>
        </Stack>
      </Paper>
    </Container>
  );
}
