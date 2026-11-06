import { Alert, Button, Divider, Group, Paper, Select, Stack, Text } from '@mantine/core';
import {
  IconCornerDownRight,
  IconLogicAnd,
  IconLogicNot,
  IconLogicOr,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react';

import type { ConditionNode, VocabularyOut } from '../../api/types';
import {
  defaultLeaf,
  isAllNode,
  isAnyNode,
  isExprNode,
  isFactNode,
  isGoalNode,
  isNotNode,
} from './conditions';
import { FactLeafEditor } from './FactLeafEditor';

interface ConditionTreeEditorProps {
  node: ConditionNode;
  onChange: (node: ConditionNode) => void;
  vocabulary: VocabularyOut[];
  disabled?: boolean;
  /** Корневой узел нельзя удалить. */
  root?: boolean;
}

/** Кнопки добавления дочерних узлов. */
function AddButtons({
  children,
  onAdd,
  vocabulary,
  disabled,
}: {
  children: ConditionNode[];
  onAdd: (next: ConditionNode[]) => void;
  vocabulary: VocabularyOut[];
  disabled: boolean;
}) {
  const addLeaf = () => {
    const fact = vocabulary[0];
    if (!fact) return;
    onAdd([...children, defaultLeaf(fact)]);
  };
  const addGroup = () => onAdd([...children, { all: [] }]);
  const addNot = () => {
    const fact = vocabulary[0];
    onAdd([...children, { not: fact ? defaultLeaf(fact) : { all: [] } }]);
  };
  return (
    <Group gap="xs">
      <Button
        size="compact-sm"
        variant="light"
        leftSection={<IconPlus size={14} />}
        onClick={addLeaf}
        disabled={disabled || vocabulary.length === 0}
      >
        Условие
      </Button>
      <Button
        size="compact-sm"
        variant="light"
        leftSection={<IconLogicAnd size={14} />}
        onClick={addGroup}
        disabled={disabled}
      >
        Группа
      </Button>
      <Button
        size="compact-sm"
        variant="light"
        leftSection={<IconLogicNot size={14} />}
        onClick={addNot}
        disabled={disabled || vocabulary.length === 0}
      >
        Не
      </Button>
    </Group>
  );
}

/** Рекурсивный редактор дерева условий: группы all/any, отрицание not, листья-факты. */
export function ConditionTreeEditor({
  node,
  onChange,
  vocabulary,
  disabled = false,
  root = false,
}: ConditionTreeEditorProps) {
  // Лист-выражение: конструктор не умеет — только чтение, правка в YAML.
  if (isExprNode(node)) {
    return (
      <Alert color="yellow" icon={<IconLogicAnd size={16} />} title="Выражение (expr)">
        <Text size="sm" ff="monospace">
          {node.expr}
        </Text>
        <Text size="xs" mt={4}>
          Условие записано выражением — конструктор его не правит. Перейдите на вкладку «YAML».
        </Text>
      </Alert>
    );
  }

  if (isGoalNode(node)) {
    return (
      <Alert color="violet" icon={<IconLogicOr size={16} />} title="Подцель (goal)">
        <Text size="sm" ff="monospace">
          {JSON.stringify(node.goal)}
        </Text>
        <Text size="xs" mt={4}>
          Подцели обратного вывода правятся только в YAML.
        </Text>
      </Alert>
    );
  }

  // Лист-факт.
  if (isFactNode(node)) {
    const known = vocabulary.some((item) => item.path === node.fact);
    if (!known) {
      return (
        <Alert color="gray" title={`Неизвестный факт: ${node.fact}`}>
          <Text size="xs">
            Такого пути нет в словаре фактов — лист можно поправить только в YAML.
          </Text>
        </Alert>
      );
    }
    return (
      <FactLeafEditor leaf={node} onChange={onChange} vocabulary={vocabulary} disabled={disabled} />
    );
  }

  // Отрицание: один дочерний узел.
  if (isNotNode(node)) {
    return (
      <Paper withBorder p="sm" radius="sm">
        <Group justify="space-between" mb="xs">
          <Group gap="xs">
            <IconLogicNot size={16} />
            <Text size="sm" fw={500}>
              Не (отрицание)
            </Text>
          </Group>
          {!root ? (
            <Button
              size="compact-xs"
              color="red"
              variant="subtle"
              leftSection={<IconTrash size={14} />}
              onClick={() => onChange({ all: [] })}
              disabled={disabled}
              aria-label="Удалить отрицание"
            >
              Удалить
            </Button>
          ) : null}
        </Group>
        <Group wrap="nowrap" gap="xs" align="flex-start">
          <IconCornerDownRight size={16} style={{ marginTop: 8, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <ConditionTreeEditor
              node={node.not as ConditionNode}
              onChange={(next) => onChange({ not: next })}
              vocabulary={vocabulary}
              disabled={disabled}
            />
          </div>
        </Group>
      </Paper>
    );
  }

  // Группа all/any (других видов в union не осталось).
  const isAll = isAllNode(node);
  const children: ConditionNode[] = isAll ? node.all : isAnyNode(node) ? node.any : [];
  const setChildren = (next: ConditionNode[]) => {
    onChange(isAll ? { all: next } : { any: next });
  };

  return (
    <Paper withBorder p="sm" radius="sm">
      <Group justify="space-between" mb="xs" wrap="wrap">
        <Group gap="xs">
          {isAll ? <IconLogicAnd size={16} /> : <IconLogicOr size={16} />}
          <Select
            aria-label="Тип группы"
            w={190}
            data={[
              { value: 'all', label: 'Все из (И)' },
              { value: 'any', label: 'Любое из (ИЛИ)' },
            ]}
            value={isAll ? 'all' : 'any'}
            onChange={(next) => {
              if (next === 'all') onChange({ all: [...children] });
              if (next === 'any') onChange({ any: [...children] });
            }}
            disabled={disabled}
            allowDeselect={false}
          />
        </Group>
        <Group gap="xs">
          <AddButtons
            children={children}
            onAdd={setChildren}
            vocabulary={vocabulary}
            disabled={disabled}
          />
          {!root ? (
            <Button
              size="compact-xs"
              color="red"
              variant="subtle"
              leftSection={<IconTrash size={14} />}
              onClick={() => onChange({ all: [] })}
              disabled={disabled}
              aria-label="Удалить группу"
            >
              Удалить
            </Button>
          ) : null}
        </Group>
      </Group>
      {children.length === 0 ? (
        <Text size="sm" c="dimmed" py="xs">
          Пусто: добавьте условие или группу. Пустая группа считается истинной.
        </Text>
      ) : (
        <Stack gap="xs">
          {children.map((child, index) => (
            <div key={index}>
              <Group wrap="nowrap" gap="xs" align="flex-start">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <ConditionTreeEditor
                    node={child}
                    onChange={(next) =>
                      setChildren(children.map((item, i) => (i === index ? next : item)))
                    }
                    vocabulary={vocabulary}
                    disabled={disabled}
                  />
                </div>
                <Button
                  size="compact-xs"
                  color="red"
                  variant="subtle"
                  aria-label={`Удалить условие ${index + 1}`}
                  onClick={() => setChildren(children.filter((_, i) => i !== index))}
                  disabled={disabled}
                  mt={6}
                >
                  <IconTrash size={14} />
                </Button>
              </Group>
              {index < children.length - 1 ? (
                <Divider
                  my="xs"
                  label={isAll ? 'и' : 'или'}
                  labelPosition="left"
                  styles={{ label: { fontSize: 12, color: 'var(--mantine-color-dimmed)' } }}
                />
              ) : null}
            </div>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
