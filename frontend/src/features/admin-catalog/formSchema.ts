import { z } from 'zod';

import type { ComponentFormValues, FrameField } from './frames';

/** Проверка числового диапазона слота (minimum/maximum/exclusive*). */
function inRange(value: number, field: FrameField): boolean {
  if (field.minimum !== undefined && value < field.minimum) return false;
  if (field.maximum !== undefined && value > field.maximum) return false;
  if (field.exclusiveMinimum !== undefined && value <= field.exclusiveMinimum) return false;
  if (field.exclusiveMaximum !== undefined && value >= field.exclusiveMaximum) return false;
  return true;
}

function rangeMessage(field: FrameField): string {
  const parts: string[] = [];
  if (field.exclusiveMinimum !== undefined) parts.push(`больше ${field.exclusiveMinimum}`);
  if (field.minimum !== undefined) parts.push(`не меньше ${field.minimum}`);
  if (field.exclusiveMaximum !== undefined) parts.push(`меньше ${field.exclusiveMaximum}`);
  if (field.maximum !== undefined) parts.push(`не больше ${field.maximum}`);
  return parts.length > 0
    ? `Диапазон: ${parts.join(', ')} ${field.unit ?? ''}`.trim()
    : 'Число вне допустимого диапазона';
}

/** Zod-правило одного числового слота (пустая строка — «не заполнено»). */
function numberRule(field: FrameField): z.ZodType<string | number> {
  return z
    .union([z.number(), z.literal('')])
    .refine((value) => !field.required || value !== '', {
      message: `Заполните поле «${field.title}»`,
    })
    .refine(
      (value) => value === '' || (field.kind === 'integer' ? Number.isInteger(value) : true),
      {
        message: 'Ожидается целое число',
      },
    )
    .refine((value) => value === '' || inRange(value, field), { message: rangeMessage(field) });
}

/** Zod-правило строкового слота (паттерн и длины из схемы фрейма). */
function stringRule(field: FrameField): z.ZodType<string | number | boolean> {
  let rule = z.union([z.string(), z.number(), z.boolean()]).transform((v) => String(v));
  rule = rule.refine((value) => !field.required || value.trim() !== '', {
    message: `Заполните поле «${field.title}»`,
  });
  if (field.minLength !== undefined && field.required) {
    rule = rule.refine((value) => value.trim().length >= field.minLength!, {
      message: `Минимум ${field.minLength} символов`,
    });
  }
  if (field.maxLength !== undefined) {
    rule = rule.refine((value) => value.length <= field.maxLength!, {
      message: `Максимум ${field.maxLength} символов`,
    });
  }
  if (field.pattern) {
    const pattern = new RegExp(field.pattern);
    rule = rule.refine((value) => value.trim() === '' || pattern.test(value.trim()), {
      message: `Недопустимое значение для «${field.title}»`,
    });
  }
  return rule;
}

/** Элементы списка через «|»: проверка паттерна и допустимых значений из схемы. */
function listItemsValid(field: FrameField, value: string): boolean {
  const items = value
    .split('|')
    .map((item) => item.trim())
    .filter((item) => item !== '');
  if (field.required && (field.minItems ?? 1) > 0 && items.length === 0) return false;
  const numeric = field.itemKind === 'integer' || field.itemKind === 'number';
  for (const item of items) {
    if (numeric) {
      const parsed = Number(item);
      if (item === '' || Number.isNaN(parsed)) return false;
      if (field.itemKind === 'integer' && !Number.isInteger(parsed)) return false;
      if (!inRange(parsed, field)) return false;
    }
    if (field.itemEnum && !field.itemEnum.map(String).includes(item)) {
      return false;
    }
    if (field.pattern && !new RegExp(field.pattern).test(item)) return false;
  }
  return true;
}

function listMessage(field: FrameField): string {
  if (field.itemEnum) {
    return `Значения через «|» из списка: ${field.itemEnum.join(', ')}`;
  }
  return field.required ? 'Укажите хотя бы одно значение через «|»' : 'Неверный формат списка';
}

/** Zod-схема формы компонента, собранная из полей фрейма категории. */
export function buildFormSchema(fields: FrameField[]): z.ZodType<ComponentFormValues> {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const raw of fields) {
    // Слот «Название» отправляем пустым: сервер собирает его из бренда и модели.
    const field = raw.name === 'name' ? { ...raw, required: false, minLength: undefined } : raw;
    switch (field.kind) {
      case 'boolean':
        shape[field.name] = z.boolean();
        break;
      case 'integer':
      case 'number':
        shape[field.name] = numberRule(field);
        break;
      case 'enum':
        shape[field.name] = stringRule(field);
        break;
      case 'list':
        shape[field.name] = z
          .union([z.string(), z.number(), z.boolean()])
          .transform((v) => String(v))
          .refine((value) => listItemsValid(field, value), { message: listMessage(field) });
        break;
      default:
        shape[field.name] = stringRule(field);
    }
  }
  return z.object(shape) as unknown as z.ZodType<ComponentFormValues>;
}
