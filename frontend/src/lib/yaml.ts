import { dump, load, YAMLException } from 'js-yaml';

/** Результат разбора YAML: либо значение, либо понятная ошибка с позицией (строка 1-based). */
export type YamlParseResult = { ok: true; value: unknown } | { ok: false; error: string };

/** Разбирает YAML и возвращает либо значение, либо текст ошибки с указанием строки и колонки. */
export function parseYaml(text: string): YamlParseResult {
  try {
    return { ok: true, value: load(text) };
  } catch (error) {
    if (error instanceof YAMLException) {
      const { line, column } = error.mark;
      return { ok: false, error: `Строка ${line + 1}, колонка ${column + 1}: ${error.reason}` };
    }
    return { ok: false, error: error instanceof Error ? error.message : 'Ошибка разбора YAML' };
  }
}

/** Сериализует значение в YAML (без переноса длинных строк, порядок ключей как у объекта). */
export function toYaml(value: unknown): string {
  return dump(value, { noRefs: true, lineWidth: -1 });
}
