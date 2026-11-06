import type { ZodType } from 'zod';

/**
 * Мост zod v4 → ошибки полей `@mantine/form`: штатный `zodResolver` собран под API zod v3.
 * Возвращает функцию валидации, понятную `useForm`; первое сообщение на поле.
 */
export function zodValidate<T>(schema: ZodType<T>) {
  return (values: T): Record<string, string | undefined> => {
    const result = schema.safeParse(values);
    if (result.success) return {};
    const errors: Record<string, string | undefined> = {};
    for (const issue of result.error.issues) {
      const key = String(issue.path[0] ?? 'form');
      errors[key] ??= issue.message;
    }
    return errors;
  };
}
