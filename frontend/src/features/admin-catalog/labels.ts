import type { ComponentSource, ComponentStatus } from '../../api/types';

export const STATUS_TITLES: Record<ComponentStatus, string> = {
  active: 'Активен',
  incomplete: 'Неполный',
  needs_kb: 'Требует знаний',
  inactive: 'Неактивен',
};

export const STATUS_COLORS: Record<ComponentStatus, string> = {
  active: 'green',
  incomplete: 'yellow',
  needs_kb: 'orange',
  inactive: 'gray',
};

/** Пояснение статуса для подсказки у бейджа. */
export const STATUS_HINTS: Record<ComponentStatus, string> = {
  active: 'Все данные есть, правила знают его характеристики. Участвует в подборе, если в наличии.',
  incomplete:
    'Не хватает данных для расчётов (индексы производительности, габариты). В подбор не попадает.',
  needs_kb:
    'Характеристика неизвестна справочникам базы знаний. В подбор не попадает, пока инженер знаний не дополнит справочник.',
  inactive: 'Снят с продажи. В новые сборки не попадает; сохранённые сборки остаются целыми.',
};

export const SOURCE_TITLES: Record<ComponentSource, string> = {
  manual: 'вручную',
  import: 'импорт',
};
