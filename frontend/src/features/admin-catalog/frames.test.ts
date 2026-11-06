import { describe, expect, it } from 'vitest';

import { buildFrameBody, frameFields, initialValues, valuesFromComponent } from './frames';
import { caseFrame, cpuFrame } from './testing/frames';

describe('frameFields', () => {
  it('разбирает слоты CPU: const-категория, enum из $defs, anyOf-null, список', () => {
    const fields = frameFields(cpuFrame);
    const byName = new Map(fields.map((field) => [field.name, field]));

    expect(byName.get('category')).toMatchObject({ kind: 'enum', constValue: 'cpu' });
    expect(byName.get('color')).toMatchObject({
      kind: 'enum',
      enum: ['black', 'white', 'silver', 'gray', 'red', 'blue', 'pink', 'other'],
    });
    expect(byName.get('cores')).toMatchObject({ kind: 'integer', minimum: 1, maximum: 128 });
    expect(byName.get('base_ghz')).toMatchObject({ kind: 'number', exclusiveMinimum: 0.5 });
    expect(byName.get('release_year')).toMatchObject({ kind: 'integer', required: false });
    expect(byName.get('perf_single')).toMatchObject({ kind: 'number', required: false });
    expect(byName.get('mem_types')).toMatchObject({
      kind: 'list',
      itemKind: 'string',
      minItems: 1,
    });
    expect(byName.get('igpu')).toMatchObject({ kind: 'boolean', required: true });
  });

  it('разбирает слоты корпуса: enum-список радиаторов с целыми значениями', () => {
    const fields = frameFields(caseFrame);
    const byName = new Map(fields.map((field) => [field.name, field]));

    expect(byName.get('size')).toMatchObject({ kind: 'enum', enum: ['mini', 'mid', 'full'] });
    expect(byName.get('radiator_support')).toMatchObject({
      kind: 'list',
      itemKind: 'integer',
      itemEnum: [120, 140, 240, 280, 360, 420],
    });
    expect(byName.get('max_gpu_mm')).toMatchObject({
      kind: 'integer',
      required: false,
      unit: 'мм',
    });
  });
});

describe('buildFrameBody', () => {
  it('собирает валидное тело CPU из значений формы (цена: рубли → копейки)', () => {
    const fields = frameFields(cpuFrame);
    const values = {
      ...initialValues('cpu', fields),
      sku: 'R5-7600',
      brand: 'AMD',
      model: 'Ryzen 5 7600',
      price_kop: 18_990,
      socket: 'AM5',
      cores: 6,
      threads: 12,
      base_ghz: 3.8,
      boost_ghz: 5.1,
      tdp_w: 105,
      igpu: true,
      mem_types: 'DDR5',
      perf_single: '',
      perf_multi: 92.4,
      release_year: 2023,
      in_stock: true,
      unlocked: false,
      cooler_included: true,
    };
    const body = buildFrameBody(values, fields);

    expect(body).toEqual({
      category: 'cpu',
      sku: 'R5-7600',
      brand: 'AMD',
      model: 'Ryzen 5 7600',
      price_kop: 1_899_000,
      socket: 'AM5',
      cores: 6,
      threads: 12,
      base_ghz: 3.8,
      boost_ghz: 5.1,
      tdp_w: 105,
      igpu: true,
      mem_types: ['DDR5'],
      release_year: 2023,
      in_stock: true,
      unlocked: false,
      cooler_included: true,
      color: 'black',
      rgb: false,
      perf_single: null,
      perf_multi: 92.4,
    });
    // Имени нет — сервер соберёт из бренда и модели.
    expect(body).not.toHaveProperty('name');
  });

  it('собирает валидное тело корпуса: enum, списки, числа из строк', () => {
    const fields = frameFields(caseFrame);
    const values = {
      ...initialValues('case', fields),
      sku: 'DP-CC560',
      brand: 'DeepCool',
      model: 'CC560',
      name: 'DeepCool CC560',
      price_kop: 5_500,
      size: 'mid',
      form_factors: 'ATX | Micro-ATX',
      psu_ff: 'ATX',
      fan_slots: 6,
      fans_included: 4,
      radiator_support: '240 | 360',
      max_gpu_mm: 370,
      max_cooler_mm: '',
      glass: true,
    };
    const body = buildFrameBody(values, fields);

    expect(body).toMatchObject({
      category: 'case',
      sku: 'DP-CC560',
      price_kop: 550_000,
      size: 'mid',
      form_factors: ['ATX', 'Micro-ATX'],
      radiator_support: [240, 360],
      max_gpu_mm: 370,
      max_cooler_mm: null,
      glass: true,
    });
  });
});

describe('valuesFromComponent', () => {
  it('круговое преобразование: карточка → значения → тело фрейма', () => {
    const fields = frameFields(caseFrame);
    const values = valuesFromComponent(
      {
        id: '9c7b0e2a-1111-2222-3333-444455556666',
        sku: 'DP-CC560',
        category: 'case',
        brand: 'DeepCool',
        model: 'CC560',
        name: 'DeepCool CC560',
        price_kop: 550_000,
        price_checked_at: null,
        price_note: null,
        in_stock: true,
        source: 'manual',
        status: 'active',
        status_issues: [],
        specs: {
          size: 'mid',
          form_factors: ['ATX', 'Micro-ATX'],
          max_gpu_mm: 370,
          max_cooler_mm: null,
          psu_ff: 'ATX',
          fan_slots: 6,
          fans_included: 4,
          radiator_support: [240, 360],
          glass: true,
          release_year: null,
          color: 'black',
          rgb: false,
        },
        perf: {},
      },
      fields,
    );

    expect(values.price_kop).toBe(5_500);
    expect(values.form_factors).toBe('ATX | Micro-ATX');
    expect(values.radiator_support).toBe('240 | 360');
    expect(values.size).toBe('mid');
    expect(values.max_cooler_mm).toBe('');
  });
});
