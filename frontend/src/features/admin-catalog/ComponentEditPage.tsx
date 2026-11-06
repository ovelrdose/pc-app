import { Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useNavigate, useParams } from 'react-router-dom';

import type { ComponentFrame, ComponentOut } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { useAdminComponent, useFrames, useReplaceComponent } from './api';
import { ComponentForm } from './ComponentForm';
import { frameFields, valuesFromComponent } from './frames';
import { STATUS_TITLES } from './labels';

/** Редактирование компонента: полная замена фреймом категории (PUT). */
export function ComponentEditPage() {
  const { id } = useParams<{ id: string }>();
  const component = useAdminComponent(id);
  const frames = useFrames();
  const replace = useReplaceComponent(id ?? '');
  const navigate = useNavigate();

  const current = component.data;
  const frame = frames.data?.find((item) => item.category === current?.category) ?? null;
  const fields = frame ? frameFields(frame) : [];

  if (component.isPending || component.error || !current || !frame) {
    return (
      <Stack gap="md">
        <Title order={3}>Компонент</Title>
        <QueryState isPending={component.isPending} error={component.error} />
      </Stack>
    );
  }

  const submit = (body: ComponentFrame) => {
    replace.mutate(body, {
      onSuccess: (saved: ComponentOut) => {
        notifications.show({
          color: 'green',
          title: 'Компонент сохранён',
          message:
            saved.status === current.status
              ? 'Статус не изменился'
              : `Новый статус: ${STATUS_TITLES[saved.status]}`,
        });
        navigate(`/admin/catalog/${saved.id}`);
      },
      onError: notifyError,
    });
  };

  return (
    <Stack gap="md">
      <div>
        <Title order={3}>{current.name}</Title>
        <Text size="sm" c="dimmed">
          {current.sku} · правка полная: отправляется весь фрейм категории
        </Text>
      </div>
      <ComponentForm
        frame={frame}
        values={valuesFromComponent(current, fields)}
        submitLabel="Сохранить"
        busy={replace.isPending}
        onSubmit={submit}
      />
    </Stack>
  );
}
