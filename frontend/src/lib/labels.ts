import type { Category, Tier } from '../api/types';

/** Русские подписи для значений API. */
export const CATEGORY_TITLES: Record<Category, string> = {
  cpu: 'Процессор',
  motherboard: 'Материнская плата',
  ram: 'Оперативная память',
  gpu: 'Видеокарта',
  ssd: 'SSD',
  hdd: 'Жёсткий диск',
  psu: 'Блок питания',
  case: 'Корпус',
  cpu_cooler: 'Кулер процессора',
  case_fan: 'Вентиляторы',
};

export const CATEGORY_ORDER: Category[] = [
  'cpu',
  'motherboard',
  'ram',
  'gpu',
  'cpu_cooler',
  'case',
  'psu',
  'ssd',
  'hdd',
  'case_fan',
];

export const TIER_TITLES: Record<Tier, string> = {
  economy: 'Эконом',
  optimum: 'Оптимум',
  maximum: 'Максимум',
};

export const TIER_DESCRIPTIONS: Record<Tier, string> = {
  economy: 'Самая дешёвая сборка, выполняющая обязательные требования',
  optimum: 'Лучшее соотношение пользы и цены',
  maximum: 'Самая производительная в пределах бюджета',
};

export const PRESET_TITLES: Record<string, string> = {
  medium: 'Средние',
  high: 'Высокие',
  ultra: 'Ультра',
};

export const SCENARIO_TITLES: Record<string, string> = {
  office: 'Офис',
  esports: 'Киберспорт',
  aaa_gaming: 'Современные игры',
  render_3d: '3D-рендер',
  video_editing: 'Монтаж',
  photo_cad: 'Фото и CAD',
  programming: 'Программирование',
  streaming: 'Стриминг',
};

export const BENCHMARK_TITLES: Record<string, string> = {
  cinebench_single: 'Cinebench 2024 (одно ядро)',
  cinebench_multi: 'Cinebench 2024 (все ядра)',
  timespy: '3DMark Time Spy',
  steel_nomad: '3DMark Steel Nomad',
};

export const VERDICT_TITLES: Record<string, string> = {
  not_found: 'Не найдено',
  in_build: 'Уже в сборке',
  not_needed: 'Категория не нужна',
  owned: 'Деталь уже есть у вас',
  unavailable: 'Недоступен',
  filtered: 'Не подходит под требования',
  incompatible: 'Несовместим с текущими деталями',
  over_budget: 'Выходит за бюджет',
  worse: 'Подходит, но хуже',
  better: 'Подходит и не хуже',
};
