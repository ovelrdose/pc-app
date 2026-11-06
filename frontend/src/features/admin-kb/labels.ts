import type { RuleKind, RuleOrigin, UserRole } from '../../api/types';

/** Виды правил: на каком этапе и как они применяются (§5.3). */
export const RULE_KIND_TITLES: Record<RuleKind, string> = {
  inference: 'Вывод',
  filter: 'Фильтр',
  compat: 'Совместимость',
  score: 'Оценка',
  validate: 'Проверка',
  goal: 'Цель',
};

export const RULE_KIND_COLORS: Record<RuleKind, string> = {
  inference: 'blue',
  filter: 'cyan',
  compat: 'red',
  score: 'grape',
  validate: 'orange',
  goal: 'violet',
};

export const RULE_ORIGIN_TITLES: Record<RuleOrigin, string> = {
  manual: 'Ручное',
  generated: 'Сгенерировано',
};

export const RULE_ORIGIN_COLORS: Record<RuleOrigin, string> = {
  manual: 'gray',
  generated: 'teal',
};

/** Типы значений фактов словаря (expert/vocabulary.py). */
export const FACT_TYPE_TITLES: Record<string, string> = {
  number: 'число',
  bool: 'да/нет',
  str: 'строка',
  list: 'список',
};

/** Кто устанавливает факт. */
export const FACT_ROLE_TITLES: Record<string, string> = {
  input: 'вход пользователя',
  derived: 'вывод правил',
  catalog: 'каталог',
  computed: 'вычисление',
};

/** Роли пользователей. */
export const USER_ROLE_TITLES: Record<UserRole, string> = {
  client: 'Клиент',
  catalog_admin: 'Админ каталога',
  knowledge_engineer: 'Инженер знаний',
  superadmin: 'Суперадмин',
};

/** Подписи операторов условия (§5.3). */
export const OP_TITLES: Record<string, string> = {
  eq: '= (равно)',
  ne: '≠ (не равно)',
  lt: '< (меньше)',
  le: '≤ (не больше)',
  gt: '> (больше)',
  ge: '≥ (не меньше)',
  in: '∈ (в списке)',
  not_in: '∉ (не в списке)',
  contains: 'содержит',
  between: 'между',
  exists: 'существует',
};

/** Операторы, предлагаемые по типу факта в конструкторе. */
export const OPS_BY_FACT_TYPE: Record<string, string[]> = {
  number: ['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'between', 'exists'],
  bool: ['eq', 'ne', 'exists'],
  str: ['eq', 'ne', 'in', 'not_in', 'contains', 'exists'],
  list: ['contains', 'in', 'not_in', 'exists'],
};
