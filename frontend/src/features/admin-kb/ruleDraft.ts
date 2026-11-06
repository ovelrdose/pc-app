import type {
  ConditionNode,
  GoalRef,
  Rule,
  RuleAction,
  RuleKind,
  RuleOrigin,
} from '../../api/types';

/** Порядок ключей тела правила в YAML-режиме (как в файлах knowledge/rules/). */
const RULE_KEY_ORDER = [
  'code',
  'name',
  'kind',
  'group',
  'priority',
  'cf',
  'enabled',
  'origin',
  'source',
  'goal',
  'when',
  'then',
  'explain',
] as const;

const RULE_KINDS: readonly RuleKind[] = [
  'inference',
  'filter',
  'compat',
  'score',
  'validate',
  'goal',
];

const RULE_ORIGINS: readonly RuleOrigin[] = ['manual', 'generated'];

/** Редактируемый черновик правила: мета + условие + действия + прочие поля тела. */
export interface RuleDraft {
  code: string;
  name: string;
  kind: RuleKind;
  group: string;
  priority: number;
  cf: number;
  explain: string;
  enabled: boolean;
  origin: RuleOrigin;
  source: string | null;
  goal: GoalRef | null;
  when: ConditionNode;
  then: RuleAction[];
}

/** Пустой лист-факт для нового правила, пока словарь не подгрузился. */
const EMPTY_WHEN: ConditionNode = {
  all: [{ fact: 'user.budget', op: 'gt', value: 0, ref: null }],
};

export function defaultDraft(): RuleDraft {
  return {
    code: '',
    name: '',
    kind: 'inference',
    group: 'profile',
    priority: 500,
    cf: 0.9,
    explain: '',
    enabled: true,
    origin: 'manual',
    source: null,
    goal: null,
    when: structuredClone(EMPTY_WHEN),
    then: [],
  };
}

function asKind(value: unknown): RuleKind {
  return RULE_KINDS.includes(value as RuleKind) ? (value as RuleKind) : 'inference';
}

function asOrigin(value: unknown): RuleOrigin {
  return RULE_ORIGINS.includes(value as RuleOrigin) ? (value as RuleOrigin) : 'manual';
}

/** Черновик из тела правила, как его отдал сервер (`RuleOut.body`). */
export function draftFromBody(body: Record<string, unknown>): RuleDraft {
  const draft = defaultDraft();
  if (typeof body.code === 'string') draft.code = body.code;
  if (typeof body.name === 'string') draft.name = body.name;
  draft.kind = asKind(body.kind);
  if (typeof body.group === 'string') draft.group = body.group;
  if (typeof body.priority === 'number') draft.priority = body.priority;
  if (typeof body.cf === 'number') draft.cf = body.cf;
  if (typeof body.explain === 'string') draft.explain = body.explain;
  if (typeof body.enabled === 'boolean') draft.enabled = body.enabled;
  draft.origin = asOrigin(body.origin);
  if (typeof body.source === 'string') draft.source = body.source;
  if (typeof body.goal === 'object' && body.goal !== null) {
    draft.goal = body.goal as GoalRef;
  }
  if (typeof body.when === 'object' && body.when !== null) {
    draft.when = body.when as ConditionNode;
  }
  if (Array.isArray(body.then)) {
    draft.then = body.then as RuleAction[];
  }
  return draft;
}

/** Тело правила по схеме DSL для POST/PUT. */
export function ruleFromDraft(draft: RuleDraft): Rule {
  const rule: Rule = {
    code: draft.code.trim(),
    name: draft.name.trim(),
    kind: draft.kind,
    group: draft.group.trim(),
    priority: draft.priority,
    cf: draft.cf,
    enabled: draft.enabled,
    origin: draft.origin,
    source: draft.source,
    goal: draft.goal,
    when: draft.when,
    explain: draft.explain.trim(),
  };
  if (draft.then.length > 0) {
    rule.then = draft.then;
  }
  return rule;
}

/** Тело правила с каноническим порядком ключей — так выглядит YAML в редакторе. */
export function canonicalBody(rule: Rule): Record<string, unknown> {
  const body: Record<string, unknown> = { ...rule };
  const ordered: Record<string, unknown> = {};
  for (const key of RULE_KEY_ORDER) {
    if (key in body && body[key] !== undefined) {
      ordered[key] = body[key];
      delete body[key];
    }
  }
  // У сгенерированных правил source не бывает null — не показываем пустым.
  if (ordered.source === null) delete ordered.source;
  if (ordered.goal === null) delete ordered.goal;
  return { ...ordered, ...body };
}

/** Краткая подпись узла для списков и подсказок. */
export function describeNodeKind(node: ConditionNode): string {
  if ('all' in node) return 'все из (И)';
  if ('any' in node) return 'любое из (ИЛИ)';
  if ('not' in node) return 'не (отрицание)';
  if ('fact' in node) return 'условие на факт';
  if ('expr' in node) return 'выражение (expr)';
  return 'подцель (goal)';
}
