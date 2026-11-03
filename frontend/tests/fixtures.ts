import type {
  BuildDetail,
  BuildItemOut,
  BuildSummary,
  ConsultationOut,
  QuestionnaireOut,
} from '../src/api/types';

export const questionnaire: QuestionnaireOut = {
  kb_version: '2026.10.1',
  steps: [
    {
      id: 'purposes',
      title: 'Задачи',
      questions: [
        {
          id: 'tasks',
          type: 'tasks',
          title: 'Для чего в основном нужен компьютер?',
          extra_title: 'Чем ещё будете заниматься иногда?',
          options: [
            { value: 'office', label: 'Офис' },
            { value: 'aaa_gaming', label: 'Современные игры' },
          ],
          allow_unknown: false,
        },
      ],
    },
    {
      id: 'budget',
      title: 'Бюджет',
      questions: [
        {
          id: 'budget',
          type: 'number',
          title: 'Сколько готовы потратить, ₽?',
          options: [],
          allow_unknown: false,
          min: 35000,
          max: 500000,
          step: 1000,
        },
      ],
    },
    {
      id: 'extras',
      title: 'Дополнительно',
      questions: [
        {
          id: 'resolution',
          type: 'choice',
          title: 'Разрешение монитора',
          options: [
            { value: '1080p', label: 'Full HD' },
            { value: '1440p', label: '2K' },
          ],
          allow_unknown: true,
        },
        { id: 'wifi', type: 'yesno', title: 'Нужен ли Wi-Fi?', options: [], allow_unknown: true },
      ],
    },
  ],
};

export function item(
  category: BuildItemOut['category'],
  name: string,
  price: number,
): BuildItemOut {
  return {
    category,
    component_id: `id-${category}-${name}`,
    sku: `${category}-${name}`,
    name,
    brand: name.split(' ')[0] ?? name,
    price_kop: price * 100,
    locked: false,
    owned: false,
  };
}

export function summary(
  id: string,
  tier: BuildSummary['tier'],
  items: BuildItemOut[],
): BuildSummary {
  return {
    id,
    tier,
    parent_build_id: null,
    total_price_kop: items.reduce((sum, i) => sum + i.price_kop, 0),
    utility: 0.5,
    items,
    title: null,
    is_saved: false,
    created_at: '2026-10-29T10:00:00Z',
  };
}

const cheap = [item('cpu', 'AMD Ryzen 5 7500F', 12000), item('gpu', 'Sapphire RX 7600', 26000)];
const strong = [item('cpu', 'AMD Ryzen 7 7700', 25000), item('gpu', 'Sapphire RX 9070 XT', 70000)];

export const consultation: ConsultationOut = {
  id: 'c1',
  status: 'completed',
  answers: { tasks: { main: 'aaa_gaming', extra: [] }, budget: 120000, resolution: '1440p' },
  owned: [],
  waived: [],
  profile: {},
  kb_version: '2026.10.1',
  catalog_revision: 1,
  builds: [
    summary('b1', 'economy', cheap),
    summary('b2', 'optimum', strong),
    summary('b3', 'maximum', strong),
  ],
  infeasibility: null,
  created_at: '2026-10-29T10:00:00Z',
};

export const buildDetail: BuildDetail = {
  ...summary('b2', 'optimum', strong),
  consultation_id: 'c1',
  kb_version: '2026.10.1',
  catalog_revision: 1,
  performance: {
    games: [
      {
        game: 'cyberpunk_2077',
        title: 'Cyberpunk 2077',
        resolution: '1440p',
        preset: 'high',
        fps: 92.4,
        low: 78,
        high: 106,
        limited_by: 'gpu',
        bottleneck_ratio: 1.3,
        vram_ok: true,
      },
    ],
    apps: [],
    benchmarks: [{ name: 'timespy', value: 29000, estimated: true }],
    balance: { fps_avg: 92.4, gpu_utilization: 0.97, limited_by: 'gpu', bottleneck_ratio: 1.3 },
    disclaimer: 'Оценка на основе референсных тестов.',
  },
  issues: [{ rule_code: 'PSU-010', action: 'warn', message: 'Запас блока питания небольшой' }],
  preferences: [],
};
