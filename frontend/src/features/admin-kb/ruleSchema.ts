import { z } from 'zod';

const RULE_KINDS = ['inference', 'filter', 'compat', 'score', 'validate', 'goal'] as const;

/** Мета-поля правила: валидируются в конструкторе (через форму редактора). */
export const ruleMetaSchema = z.object({
  code: z
    .string()
    .min(1, 'Укажите код правила')
    .regex(
      /^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$/,
      'Код латиницей в верхнем регистре: PREFIX-NNN (BUD-014) или GEN-…',
    ),
  name: z.string().min(1, 'Укажите название'),
  kind: z.enum(RULE_KINDS),
  group: z.string().min(1, 'Укажите группу (например, budget)'),
  priority: z.number({ message: 'Приоритет — целое число' }).int('Приоритет — целое число'),
  cf: z
    .number({ message: 'CF — число от 0 до 1' })
    .min(0, 'CF не бывает меньше 0')
    .max(1, 'CF не бывает больше 1'),
  explain: z.string().min(1, 'Объяснение (explain) обязательно: как оно попадёт в ответ клиенту'),
  enabled: z.boolean(),
});

export type RuleMetaValues = z.infer<typeof ruleMetaSchema>;

/** Всё тело правила перед сохранением (when проверяет только форму узла; глубже — сервер). */
export const ruleBodySchema = ruleMetaSchema.extend({
  origin: z.enum(['manual', 'generated']),
  source: z.string().nullable().optional(),
  goal: z.unknown().nullable().optional(),
  when: z
    .unknown()
    .refine(
      (value) => typeof value === 'object' && value !== null && !Array.isArray(value),
      'Условие when должно быть объектом: {all: […]}, {any: […]}, {not: …} или листом',
    ),
  then: z.array(z.unknown()).optional(),
});
