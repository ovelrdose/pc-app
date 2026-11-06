import type { Category, ComponentOut, FrameOut } from '../../api/types';

/**
 * Построение форм компонента из JSON Schema фрейма (`GET /frames`).
 * Схема пишется Pydantic: перечисления — в `$defs`, необязательные поля — `anyOf [T, null]`,
 * у слотов есть русский `title` и единицы `unit`.
 */

/** Тип значения слота в форме: строки, числа, булевы; пустая строка — «не заполнено». */
export type SlotFormValue = string | number | boolean;

export interface ComponentFormValues {
  category: string;
  [slot: string]: SlotFormValue;
}

/** Поле формы, собранное из свойства JSON Schema фрейма. */
export interface FrameField {
  name: string;
  title: string;
  kind: 'string' | 'integer' | 'number' | 'boolean' | 'enum' | 'list';
  required: boolean;
  /** Тип элементов списка (для kind = 'list'). */
  itemKind?: 'string' | 'integer' | 'number' | 'enum';
  unit?: string;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  /** Допустимые значения (для enum и list с itemKind = 'enum'). */
  enum?: string[];
  itemEnum?: (string | number)[];
  defaultValue?: unknown;
  /** Значение-константа (дискриминатор категории). */
  constValue?: string;
  /** Минимальное число элементов списка. */
  minItems?: number;
}

interface JsonSchemaNode {
  type?: string;
  title?: string;
  description?: string;
  unit?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number | boolean;
  exclusiveMaximum?: number | boolean;
  minItems?: number;
  items?: JsonSchemaNode;
  $ref?: string;
  anyOf?: JsonSchemaNode[];
}

interface FrameJsonSchema {
  properties?: Record<string, JsonSchemaNode>;
  required?: string[];
  $defs?: Record<string, JsonSchemaNode>;
}

/** Разворачивает `$ref` вида `#/$defs/Имя` и вариант `anyOf [T, null]` в исходную схему слота. */
function resolveNode(node: JsonSchemaNode, defs: Record<string, JsonSchemaNode>): JsonSchemaNode {
  let current = node;
  if (current.$ref) {
    const name = current.$ref.replace('#/$defs/', '');
    const target = defs[name];
    if (target) {
      // Рядом с $ref могут лежать title/default — сохраняем их.
      current = {
        ...target,
        ...Object.fromEntries(Object.entries(current).filter(([k]) => k !== '$ref')),
      };
    }
  }
  if (current.anyOf) {
    const nonNull = current.anyOf.find((variant) => variant.type !== 'null');
    if (nonNull) {
      current = {
        ...nonNull,
        title: current.title ?? nonNull.title,
        default: current.default ?? nonNull.default,
        unit: current.unit ?? nonNull.unit,
      };
    }
  }
  return current;
}

function asNumber(value: number | boolean | undefined): number | undefined {
  return typeof value === 'number' ? value : undefined;
}

function asStringArray(values: unknown[] | undefined): string[] | undefined {
  if (!values) return undefined;
  const strings = values.filter((value): value is string => typeof value === 'string');
  return strings.length > 0 ? strings : undefined;
}

/** Парсит JSON Schema фрейма в список полей формы (в порядке следования слотов фрейма). */
export function frameFields(frame: FrameOut): FrameField[] {
  const schema = frame.json_schema as FrameJsonSchema;
  const defs = schema.$defs ?? {};
  const required = new Set(schema.required ?? []);
  const fields: FrameField[] = [];
  for (const [name, raw] of Object.entries(schema.properties ?? {})) {
    const node = resolveNode(raw, defs);
    const base: FrameField = {
      name,
      title: node.title ?? name,
      kind: 'string',
      required: required.has(name),
      unit: node.unit,
      pattern: node.pattern,
      minLength: node.minLength,
      maxLength: node.maxLength,
      minimum: asNumber(node.minimum),
      maximum: asNumber(node.maximum),
      exclusiveMinimum: asNumber(node.exclusiveMinimum),
      exclusiveMaximum: asNumber(node.exclusiveMaximum),
      defaultValue: node.default,
    };
    if (node.const !== undefined) {
      fields.push({
        ...base,
        kind: 'enum',
        constValue: String(node.const),
        enum: [String(node.const)],
      });
      continue;
    }
    if (node.enum) {
      const strings = asStringArray(node.enum);
      if (node.type === 'integer' || node.type === 'number') {
        // Целочисленное перечисление (например, обороты HDD) — селект с числами.
        fields.push({
          ...base,
          kind: 'enum',
          enum: node.enum.map((value) => String(value)),
          itemKind: node.type,
        });
      } else {
        fields.push({ ...base, kind: 'enum', enum: strings ?? [] });
      }
      continue;
    }
    switch (node.type) {
      case 'boolean':
        fields.push({ ...base, kind: 'boolean', defaultValue: node.default ?? false });
        break;
      case 'integer':
      case 'number':
        fields.push({ ...base, kind: node.type });
        break;
      case 'array': {
        const items = node.items ? resolveNode(node.items, defs) : undefined;
        const field: FrameField = {
          ...base,
          kind: 'list',
          // Тип элементов сохраняем: у списков-перечислений (радиаторы, обороты) это числа.
          itemKind: items?.type === 'integer' || items?.type === 'number' ? items.type : 'string',
          minItems: node.minItems,
        };
        if (items?.enum) {
          field.itemEnum = items.enum.filter(
            (value): value is string | number =>
              typeof value === 'string' || typeof value === 'number',
          );
        } else if (items?.pattern) {
          field.pattern = items.pattern;
        }
        fields.push(field);
        break;
      }
      default:
        fields.push(base);
    }
  }
  return fields;
}

/** Начальные значения формы нового компонента: дефолты фрейма, остальное — пустое. */
export function initialValues(category: Category, fields: FrameField[]): ComponentFormValues {
  const values: ComponentFormValues = { category };
  for (const field of fields) {
    if (field.constValue !== undefined) {
      values[field.name] = field.constValue;
    } else if (field.kind === 'boolean') {
      values[field.name] = field.defaultValue === true;
    } else if (field.kind === 'enum' && field.defaultValue !== undefined) {
      values[field.name] = String(field.defaultValue);
    } else {
      values[field.name] = '';
    }
  }
  return values;
}

/** Значения формы из карточки компонента: `specs` + `perf` + колонки таблицы. */
export function valuesFromComponent(
  component: ComponentOut,
  fields: FrameField[],
): ComponentFormValues {
  const source: Record<string, unknown> = {
    ...component.specs,
    ...component.perf,
    sku: component.sku,
    brand: component.brand,
    model: component.model,
    name: component.name,
    price_kop: component.price_kop / 100,
    in_stock: component.in_stock,
  };
  const values: ComponentFormValues = { category: component.category };
  for (const field of fields) {
    const raw = source[field.name];
    switch (field.kind) {
      case 'boolean':
        values[field.name] = raw === true;
        break;
      case 'integer':
      case 'number':
        values[field.name] = typeof raw === 'number' ? raw : '';
        break;
      case 'list': {
        if (Array.isArray(raw)) {
          values[field.name] = raw.map((item) => String(item)).join(' | ');
        } else {
          values[field.name] = '';
        }
        break;
      }
      default:
        values[field.name] = raw === null || raw === undefined ? '' : String(raw);
    }
  }
  return values;
}

/**
 * Собирает тело создания/замены компонента (фрейм категории) из значений формы.
 * Цена вводится в рублях и переводится в копейки; пустые необязательные слоты — в `null`,
 * пустые списки — в `[]`; слот `name` пустым не отправляется (сервер соберёт из бренда и модели).
 */
export function buildFrameBody(
  values: ComponentFormValues,
  fields: FrameField[],
): Record<string, unknown> {
  const body: Record<string, unknown> = { category: values.category };
  for (const field of fields) {
    if (field.name === 'category') continue;
    const value = values[field.name];
    if (field.constValue !== undefined) {
      body[field.name] = field.constValue;
      continue;
    }
    if (field.name === 'name' && (value === undefined || String(value).trim() === '')) {
      continue;
    }
    switch (field.kind) {
      case 'boolean':
        body[field.name] = value === true;
        break;
      case 'integer':
      case 'number': {
        if (field.name === 'price_kop') {
          // В форме цена — в рублях; API принимает копейки.
          body[field.name] =
            value === '' || value === undefined ? null : Math.round(Number(value) * 100);
        } else if (value === '' || value === undefined) {
          body[field.name] = null;
        } else {
          body[field.name] = Number(value);
        }
        break;
      }
      case 'enum': {
        const text = value === undefined ? '' : String(value).trim();
        if (text === '') {
          body[field.name] = null;
        } else if (field.itemKind === 'integer' || field.itemKind === 'number') {
          body[field.name] = Number(text);
        } else {
          body[field.name] = text;
        }
        break;
      }
      case 'list': {
        const text = value === undefined ? '' : String(value).trim();
        const items =
          text === ''
            ? []
            : text
                .split('|')
                .map((item) => item.trim())
                .filter((item) => item !== '');
        if (field.itemKind === 'integer' || field.itemKind === 'number') {
          body[field.name] = items.map((item) => Number(item));
        } else {
          body[field.name] = items;
        }
        break;
      }
      default: {
        const text = value === undefined ? '' : String(value).trim();
        body[field.name] = text === '' ? null : text;
      }
    }
  }
  return body;
}
