import { describe, expect, it } from 'vitest';

import type { ConditionNode } from '../../api/types';
import { parseYaml, toYaml } from '../../lib/yaml';
import {
  defaultLeaf,
  isConditionNode,
  leafUsesRef,
  opNeedsValue,
  opsForFact,
  treeHasExpr,
} from './conditions';
import { canonicalBody, defaultDraft, draftFromBody, ruleFromDraft } from './ruleDraft';
import { vocabularyFixture } from './testing/fixtures';

const fact = (path: string) => vocabularyFixture.find((item) => item.path === path);

describe('conditions: типы узлов', () => {
  it('распознаёт группы, листья, выражения и подцели', () => {
    expect(isConditionNode({ all: [] })).toBe(true);
    expect(isConditionNode({ any: [] })).toBe(true);
    expect(isConditionNode({ not: { all: [] } })).toBe(true);
    expect(isConditionNode({ fact: 'user.budget', op: 'gt', value: 0 })).toBe(true);
    expect(isConditionNode({ expr: 'a < b' })).toBe(true);
    expect(isConditionNode({ goal: { predicate: 'runs_game', args: {} } })).toBe(true);
    expect(isConditionNode(null)).toBe(false);
    expect(isConditionNode('str')).toBe(false);
    expect(isConditionNode({ foo: 1 })).toBe(false);
  });

  it('находит expr на любой глубине дерева', () => {
    const tree: ConditionNode = {
      all: [
        { any: [{ not: { expr: 'build.psu.wattage < 100' } }] },
        { fact: 'user.budget', op: 'gt', value: 0 },
      ],
    };
    expect(treeHasExpr(tree)).toBe(true);
    const plain: ConditionNode = {
      all: [{ fact: 'user.budget', op: 'gt', value: 0 }],
    };
    expect(treeHasExpr(plain)).toBe(false);
  });

  it('подбирает операторы по типу факта', () => {
    expect(opsForFact(fact('user.budget'))).toContain('ge');
    expect(opsForFact(fact('user.resolution'))).toContain('in');
    expect(opsForFact(fact('user.wants_rgb'))).toEqual(['eq', 'ne', 'exists']);
    expect(opsForFact(undefined)).toEqual(['eq']);
    expect(opNeedsValue('exists')).toBe(false);
    expect(opNeedsValue('eq')).toBe(true);
  });

  it('строит лист по умолчанию под тип факта', () => {
    expect(defaultLeaf(fact('user.budget')!)).toEqual({
      fact: 'user.budget',
      op: 'eq',
      value: 0,
      ref: null,
    });
    expect(defaultLeaf(fact('user.resolution')!).op).toBe('in');
    expect(defaultLeaf(fact('user.wants_rgb')!).value).toBe(true);
    expect(defaultLeaf(fact('user.games')!).op).toBe('contains');
    expect(leafUsesRef({ fact: 'a', op: 'eq', value: 1, ref: 'b' })).toBe(true);
    expect(leafUsesRef({ fact: 'a', op: 'eq', value: 1, ref: null })).toBe(false);
  });
});

describe('ruleDraft: дерево условий ↔ тело правила', () => {
  it('собирает body правила из дерева all/any/not без потерь', () => {
    const when: ConditionNode = {
      all: [
        { fact: 'user.resolution', op: 'eq', value: '2160p' },
        {
          any: [
            { fact: 'profile.gaming_weight', op: 'ge', value: 0.5 },
            { not: { fact: 'user.wants_rgb', op: 'eq', value: true } },
          ],
        },
      ],
    };
    const draft = { ...defaultDraft(), code: 'TST-001', name: 'Тест', explain: 'Пояснение', when };
    const rule = ruleFromDraft(draft);
    expect(rule.when).toEqual(when);
    expect(rule.code).toBe('TST-001');
    expect(rule.origin).toBe('manual');
  });

  it('читает draft обратно из body (в том числе с expr-листом)', () => {
    const body = {
      code: 'CMP-021',
      name: 'Запас мощности БП',
      kind: 'compat',
      group: 'compatibility',
      priority: 900,
      cf: 1,
      enabled: true,
      origin: 'manual',
      when: { expr: 'build.psu.wattage < (build.cpu.tdp_w + build.gpu.tbp_w + 75) * 1.3' },
      then: [{ action: 'reject', message: 'БП слабоват' }],
      explain: 'Нужен запас 30%.',
    };
    const draft = draftFromBody(body);
    expect(draft.code).toBe('CMP-021');
    expect(draft.kind).toBe('compat');
    expect(draft.cf).toBe(1);
    expect(draft.then).toHaveLength(1);
    expect(treeHasExpr(draft.when)).toBe(true);
    // expr-узел не ломается при обратной сборке
    const rule = ruleFromDraft(draft);
    expect(rule.when).toEqual(body.when);
    expect(rule.then).toEqual(body.then);
  });

  it('канонический порядок ключей тела совпадает с файлами знаний', () => {
    const draft = defaultDraft();
    const ordered = Object.keys(canonicalBody(ruleFromDraft(draft)));
    expect(ordered.slice(0, 7)).toEqual([
      'code',
      'name',
      'kind',
      'group',
      'priority',
      'cf',
      'enabled',
    ]);
    expect(ordered).not.toContain('goal');
    expect(ordered).not.toContain('source');
  });

  it('YAML-круг: тело → текст → тело сохраняет условие с expr', () => {
    const draft = draftFromBody({
      code: 'CMP-021',
      name: 'Запас мощности',
      kind: 'compat',
      group: 'compatibility',
      priority: 900,
      cf: 1,
      enabled: true,
      origin: 'manual',
      when: {
        all: [{ expr: 'build.psu.wattage < 500' }, { fact: 'user.budget', op: 'gt', value: 0 }],
      },
      explain: 'Пояснение.',
    });
    const yamlText = toYaml(canonicalBody(ruleFromDraft(draft)));
    const parsed = parseYaml(yamlText);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const again = draftFromBody(parsed.value as Record<string, unknown>);
    expect(again.when).toEqual(draft.when);
  });

  it('ошибка YAML показывает строку и колонку', () => {
    const parsed = parseYaml('a: [1,\n  b: }');
    expect(parsed.ok).toBe(false);
    if (parsed.ok) return;
    expect(parsed.error).toMatch(/Строка \d+, колонка \d+/);
  });
});
