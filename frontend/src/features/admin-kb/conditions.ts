import type {
  AllCondition,
  AnyCondition,
  ConditionNode,
  FactCondition,
  GoalCondition,
  NotCondition,
  Op,
  VocabularyOut,
} from '../../api/types';
import { OPS_BY_FACT_TYPE } from './labels';

export function isAllNode(node: ConditionNode): node is AllCondition {
  return 'all' in node && Array.isArray(node.all);
}

export function isAnyNode(node: ConditionNode): node is AnyCondition {
  return 'any' in node && Array.isArray(node.any);
}

export function isNotNode(node: ConditionNode): node is NotCondition {
  return 'not' in node && typeof node.not === 'object' && node.not !== null;
}

export function isFactNode(node: ConditionNode): node is FactCondition {
  return 'fact' in node && typeof node.fact === 'string';
}

export function isExprNode(node: ConditionNode): node is { expr: string } {
  return 'expr' in node && typeof node.expr === 'string';
}

export function isGoalNode(node: ConditionNode): node is GoalCondition {
  return 'goal' in node && typeof node.goal === 'object' && node.goal !== null;
}

/** Похоже ли значение на узел дерева условий (после разбора YAML). */
export function isConditionNode(value: unknown): value is ConditionNode {
  if (typeof value !== 'object' || value === null) return false;
  const keys = Object.keys(value);
  return (
    keys.includes('all') ||
    keys.includes('any') ||
    keys.includes('not') ||
    keys.includes('fact') ||
    keys.includes('expr') ||
    keys.includes('goal')
  );
}

/** Дерево содержит лист-выражение (`expr`) или подцель (`goal`) — конструктор их не правит. */
export function treeHasExpr(node: ConditionNode): boolean {
  if (isExprNode(node) || isGoalNode(node)) return true;
  if (isAllNode(node)) return node.all.some((child) => treeHasExpr(child as ConditionNode));
  if (isAnyNode(node)) return node.any.some((child) => treeHasExpr(child as ConditionNode));
  if (isNotNode(node)) return treeHasExpr(node.not as ConditionNode);
  return false;
}

/** Операторы по типу факта (по словарю). */
export function opsForFact(fact: VocabularyOut | undefined): Op[] {
  if (!fact) return ['eq'];
  return (OPS_BY_FACT_TYPE[fact.type] ?? ['eq']) as Op[];
}

/** Новый лист-условие по умолчанию для выбранного факта. */
export function defaultLeaf(fact: VocabularyOut): FactCondition {
  switch (fact.type) {
    case 'number':
      return { fact: fact.path, op: 'eq', value: 0, ref: null };
    case 'bool':
      return { fact: fact.path, op: 'eq', value: true, ref: null };
    case 'list':
      return { fact: fact.path, op: 'contains', value: '', ref: null };
    default:
      return fact.values.length > 0
        ? {
            fact: fact.path,
            op: 'in',
            value: [fact.values[0] as string | number | boolean],
            ref: null,
          }
        : { fact: fact.path, op: 'eq', value: '', ref: null };
  }
}

/** Для оператора `exists` значение не нужно. */
export function opNeedsValue(op: Op): boolean {
  return op !== 'exists';
}

/** Лист ссылается на другой факт (ref), а не на литерал. */
export function leafUsesRef(leaf: FactCondition): boolean {
  return typeof leaf.ref === 'string' && leaf.ref.length > 0;
}
