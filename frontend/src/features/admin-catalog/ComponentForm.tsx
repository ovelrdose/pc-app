import { Button, Group, NumberInput, Paper, Select, Stack, Switch, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMemo } from 'react';

import type { ComponentFrame, FrameOut } from '../../api/types';
import { zodValidate } from '../../lib/validate';
import { buildFormSchema } from './formSchema';
import { buildFrameBody, frameFields, type ComponentFormValues } from './frames';

interface ComponentFormProps {
  frame: FrameOut;
  /** Начальные значения (новый компонент — `initialValues`, правка — `valuesFromComponent`). */
  values: ComponentFormValues;
  submitLabel: string;
  busy: boolean;
  onSubmit: (body: ComponentFrame) => void;
}

function unitSuffix(unit: string | undefined): string | undefined {
  return unit ? `, ${unit}` : undefined;
}

/**
 * Форма компонента, построенная из JSON Schema фрейма категории (`GET /frames`):
 * enum-слоты — селекты со значениями схемы, цена — в рублях (в API — копейки).
 */
export function ComponentForm({ frame, values, submitLabel, busy, onSubmit }: ComponentFormProps) {
  const fields = useMemo(() => frameFields(frame), [frame]);
  const schema = useMemo(() => buildFormSchema(fields), [fields]);
  const form = useForm<ComponentFormValues>({
    mode: 'controlled',
    initialValues: values,
    validate: zodValidate(schema),
  });

  const submit = form.onSubmit((current) => {
    onSubmit(buildFrameBody(current, fields) as unknown as ComponentFrame);
  });

  return (
    <Paper withBorder p="lg" radius="md" component="form" onSubmit={(event) => void submit(event)}>
      <Stack gap="sm">
        {fields.map((field) => {
          if (field.constValue !== undefined) {
            return (
              <TextInput
                key={field.name}
                label={field.title}
                value={frame.title}
                disabled
                w={280}
              />
            );
          }
          if (field.name === 'name') {
            return (
              <TextInput
                key={field.name}
                label="Название"
                description="Необязательно: если пусто, соберётся из бренда и модели"
                {...form.getInputProps('name')}
                w={440}
              />
            );
          }
          if (field.name === 'price_kop') {
            return (
              <NumberInput
                key={field.name}
                label="Цена"
                description="В рублях; в базе хранится в копейках"
                min={1}
                required
                w={280}
                {...form.getInputProps('price_kop')}
              />
            );
          }
          switch (field.kind) {
            case 'boolean':
              return (
                <Switch
                  key={field.name}
                  label={`${field.title}${unitSuffix(field.unit) ?? ''}`}
                  {...form.getInputProps(field.name, { type: 'checkbox' })}
                />
              );
            case 'enum':
              return (
                <Select
                  key={field.name}
                  label={`${field.title}${unitSuffix(field.unit) ?? ''}`}
                  data={(field.enum ?? []).map((value) => ({ value, label: value }))}
                  clearable={!field.required}
                  required={field.required}
                  w={320}
                  {...form.getInputProps(field.name)}
                />
              );
            case 'integer':
            case 'number':
              return (
                <NumberInput
                  key={field.name}
                  label={`${field.title}${unitSuffix(field.unit) ?? ''}`}
                  description={
                    field.required ? undefined : 'Оставьте пустым, если характеристика неизвестна'
                  }
                  required={field.required}
                  w={280}
                  {...form.getInputProps(field.name)}
                />
              );
            case 'list':
              return (
                <TextInput
                  key={field.name}
                  label={`${field.title}${unitSuffix(field.unit) ?? ''}`}
                  description={
                    field.itemEnum
                      ? `Значения через «|» из списка: ${field.itemEnum.join(', ')}`
                      : 'Список значений через «|», например: AM5 | LGA1700'
                  }
                  required={field.required}
                  w={440}
                  {...form.getInputProps(field.name)}
                />
              );
            default:
              return (
                <TextInput
                  key={field.name}
                  label={`${field.title}${unitSuffix(field.unit) ?? ''}`}
                  required={field.required}
                  w={440}
                  {...form.getInputProps(field.name)}
                />
              );
          }
        })}
        <Group mt="md">
          <Button type="submit" loading={busy}>
            {submitLabel}
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
