import type {
  RegenerateOut,
  RuleDetailOut,
  RuleOut,
  RuleTestOut,
  SnapshotOut,
  UserAdminPage,
  ValidateReportOut,
  VocabularyOut,
} from '../../../api/types';

/** Мини-словарь фактов для конструктора условий (соответствует VocabularyOut). */
export const vocabularyFixture: VocabularyOut[] = [
  { path: 'user.budget', type: 'number', role: 'input', title: 'Бюджет, ₽', values: [] },
  {
    path: 'user.resolution',
    type: 'str',
    role: 'input',
    title: 'Разрешение монитора',
    values: ['1080p', '1440p', '2160p'],
  },
  { path: 'user.wants_rgb', type: 'bool', role: 'input', title: 'Нужна подсветка', values: [] },
  { path: 'user.games', type: 'list', role: 'input', title: 'Игры клиента', values: [] },
  {
    path: 'profile.gaming_weight',
    type: 'number',
    role: 'derived',
    title: 'Вес гейминга',
    values: [],
  },
  {
    path: 'budget.share.gpu',
    type: 'number',
    role: 'derived',
    title: 'Доля бюджета на GPU',
    values: [],
  },
];

export function ruleOut(partial: Partial<RuleOut> & Pick<RuleOut, 'code'>): RuleOut {
  return {
    kind: 'inference',
    group: 'budget',
    name: `Правило ${partial.code}`,
    priority: 500,
    cf: 0.9,
    enabled: true,
    origin: 'manual',
    source: null,
    explain: 'Объяснение правила',
    revision: 1,
    updated_by: null,
    updated_at: '2026-11-05T10:00:00',
    body: {
      code: partial.code,
      name: `Правило ${partial.code}`,
      kind: 'inference',
      group: 'budget',
      priority: 500,
      cf: 0.9,
      enabled: true,
      origin: 'manual',
      when: { all: [{ fact: 'user.budget', op: 'gt', value: 0 }] },
      then: [{ action: 'assert', fact: 'budget.share.gpu', value: 0.4 }],
      explain: 'Объяснение правила',
    },
    ...partial,
  };
}

/** Правило BUD-014 с деревом условий из файла знаний. */
export function ruleDetailFixture(): RuleDetailOut {
  const body: Record<string, unknown> = {
    code: 'BUD-014',
    name: '4K-гейминг смещает бюджет в видеокарту',
    kind: 'inference',
    group: 'budget',
    priority: 500,
    cf: 0.9,
    enabled: true,
    origin: 'manual',
    when: {
      all: [
        { fact: 'user.resolution', op: 'eq', value: '2160p' },
        { fact: 'profile.gaming_weight', op: 'ge', value: 0.5 },
      ],
    },
    then: [
      { action: 'assert', fact: 'budget.share.gpu', value: 0.45 },
      { action: 'assert', fact: 'budget.share.cpu', value: 0.18 },
    ],
    explain: 'Для игр в 4K главная нагрузка ложится на видеокарту.',
  };
  return {
    rule: ruleOut({ code: 'BUD-014', name: '4K-гейминг смещает бюджет в видеокарту', body }),
    revisions: [
      {
        revision: 1,
        body,
        change_type: 'seed',
        author_id: null,
        created_at: '2026-11-01T09:00:00',
      },
    ],
  };
}

/** Отчёт валидации с ошибками, предупреждениями и упавшим эталонным кейсом. */
export const validateReportFixture: ValidateReportOut = {
  rules_total: 531,
  errors: [
    'CMP-012: слот `lenght_mm` не существует во фрейме «Видеокарта»',
    'BUD-031: цикл PRF-011 → REQ-007 → PRF-011',
  ],
  warnings: ['SCR-012 дублирует SCR-004'],
  golden: {
    passed: 15,
    failed: 1,
    failures: { 'G-012': ['офис за 35 000 ₽: превышен бюджет на 2 400 ₽'] },
  },
  checksum: 'abcdef1234567890fedc',
  matches_latest: false,
};

export const snapshotsFixture: SnapshotOut[] = [
  {
    id: 15,
    version: 15,
    checksum: 'abcdef1234567890',
    comment: 'новые правила AM6',
    published_by: 'engineer@sborshik.local',
    published_at: '2026-11-05T09:00:00',
    rules: 531,
    warnings: 3,
    golden: 16,
  },
  {
    id: 14,
    version: 14,
    checksum: '0123456789abcdef',
    comment: null,
    published_by: null,
    published_at: '2026-11-01T18:30:00',
    rules: 530,
    warnings: 2,
    golden: 16,
  },
];

export const regenerateFixture: RegenerateOut = {
  dry_run: true,
  created: ['GEN-GAME-GTA6-ULTRA'],
  updated: ['GEN-CHP-B950-TDP'],
  removed: ['GEN-GAME-OLDSOUL-HIGH'],
  overrides: ['GEN-SKT-AM5-FUTURE'],
};

export const usersFixture: UserAdminPage = {
  items: [
    {
      id: 'u-1',
      email: 'admin@sborshik.local',
      role: 'superadmin',
      is_active: true,
      created_at: '2026-10-01T12:00:00',
    },
    {
      id: 'u-2',
      email: 'engineer@sborshik.local',
      role: 'knowledge_engineer',
      is_active: true,
      created_at: '2026-10-05T12:00:00',
    },
    {
      id: 'u-3',
      email: 'blocked@sborshik.local',
      role: 'client',
      is_active: false,
      created_at: '2026-10-10T12:00:00',
    },
  ],
  total: 3,
  limit: 25,
  offset: 0,
};

export const ruleTestResultFixture: RuleTestOut = {
  matched: true,
  premise_cf: 0.9,
  actions: [
    {
      action: 'assert',
      fact: 'budget.share.gpu',
      value: 0.45,
      message: null,
      weight: null,
      category: null,
      target: null,
    },
    {
      action: 'assert',
      fact: 'budget.share.cpu',
      value: 0.18,
      message: null,
      weight: null,
      category: null,
      target: null,
    },
  ],
  facts_after: [
    { path: 'budget.share.gpu', value: 0.45, cf: 0.9 },
    { path: 'budget.share.cpu', value: 0.18, cf: 0.9 },
    { path: 'user.budget', value: 90000, cf: 1 },
  ],
  failures: [],
};
