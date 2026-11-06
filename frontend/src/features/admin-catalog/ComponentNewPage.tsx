import { Select, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Category, ComponentFrame, ComponentOut } from '../../api/types';
import { CATEGORY_TITLES, CATEGORY_ORDER } from '../../lib/labels';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { useCreateComponent, useFrames } from './api';
import { ComponentForm } from './ComponentForm';
import { frameFields, initialValues } from './frames';

/** Создание компонента: сначала категория, затем форма из фрейма категории. */
export function ComponentNewPage() {
  const frames = useFrames();
  const [category, setCategory] = useState<Category | null>(null);
  const create = useCreateComponent();
  const navigate = useNavigate();

  const frame = frames.data?.find((item) => item.category === category) ?? null;
  const fields = frame ? frameFields(frame) : [];

  const submit = (body: ComponentFrame) => {
    create.mutate(body, {
      onSuccess: (component: ComponentOut) => {
        notifications.show({
          color: 'green',
          title: 'Компонент создан',
          message: `${component.name}: ${component.status === 'active' ? 'активен' : 'проверьте статус'}`,
        });
        navigate(`/admin/catalog/${component.id}`);
      },
      onError: notifyError,
    });
  };

  return (
    <Stack gap="md">
      <Title order={3}>Новый компонент</Title>
      <QueryState isPending={frames.isPending} error={frames.error} />
      {frames.data ? (
        <>
          <Select
            label="Категория"
            placeholder="Выберите категорию"
            w={320}
            data={CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_TITLES[value] }))}
            value={category}
            onChange={(value) => setCategory((value as Category | null) ?? null)}
          />
          {frame ? (
            <ComponentForm
              key={frame.category}
              frame={frame}
              values={initialValues(frame.category, fields)}
              submitLabel="Создать"
              busy={create.isPending}
              onSubmit={submit}
            />
          ) : (
            <Text c="dimmed" size="sm">
              Выберите категорию — форма соберётся из фрейма: поля, единицы и допустимые значения.
            </Text>
          )}
        </>
      ) : null}
    </Stack>
  );
}
