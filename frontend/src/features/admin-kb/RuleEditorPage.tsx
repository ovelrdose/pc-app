import {
  Alert,
  Badge,
  Button,
  Divider,
  Group,
  Modal,
  NumberInput,
  Paper,
  Select,
  Stack,
  Switch,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import {
  IconArrowLeft,
  IconDeviceFloppy,
  IconInfoCircle,
  IconPlayerStop,
  IconTestPipe,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import type { ConditionNode, Rule } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { parseYaml, toYaml } from '../../lib/yaml';
import { zodValidate } from '../../lib/validate';
import { CodeEditor } from '../../components/CodeEditor';
import { QueryState } from '../../components/QueryState';
import { useCreateRule, useReplaceRule, useRetireRule, useRule, useVocabulary } from './api';
import { ConditionTreeEditor } from './ConditionTreeEditor';
import { defaultLeaf, isConditionNode, isFactNode, treeHasExpr } from './conditions';
import { RULE_KIND_TITLES } from './labels';
import { canonicalBody, defaultDraft, draftFromBody, ruleFromDraft } from './ruleDraft';
import { ruleBodySchema, ruleMetaSchema } from './ruleSchema';

const KIND_OPTIONS = (Object.keys(RULE_KIND_TITLES) as Rule['kind'][]).map((value) => ({
  value,
  label: RULE_KIND_TITLES[value],
}));

/** Редактор правила: вкладки «Конструктор» (мета + дерево условий) и «YAML» (всё тело). */
export function RuleEditorPage() {
  const params = useParams<{ code: string }>();
  const isNew = params.code === undefined;
  const navigate = useNavigate();

  const ruleQuery = useRule(isNew ? undefined : params.code);
  const vocabulary = useVocabulary();
  const createRule = useCreateRule();
  const replaceRule = useReplaceRule(params.code ?? '');
  const retireRule = useRetireRule();

  const [draft, setDraft] = useState(() => defaultDraft());
  const [loadedCode, setLoadedCode] = useState<string | null>(null);
  const [tab, setTab] = useState<string>('constructor');
  const [yamlText, setYamlText] = useState('');
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<string[]>([]);
  const [retireOpen, setRetireOpen] = useState(false);

  const form = useForm({
    initialValues: {
      code: '',
      name: '',
      kind: 'inference' as Rule['kind'],
      group: 'profile',
      priority: 500,
      cf: 0.9,
      explain: '',
      enabled: true,
    },
    validate: zodValidate(ruleMetaSchema),
  });

  // Загрузка существующего правила в форму и черновик.
  useEffect(() => {
    if (isNew || !ruleQuery.data || loadedCode === params.code) return;
    const body = ruleQuery.data.rule.body;
    const nextDraft = draftFromBody(body);
    setDraft(nextDraft);
    setLoadedCode(params.code ?? null);
    form.setValues({
      code: nextDraft.code,
      name: nextDraft.name,
      kind: nextDraft.kind,
      group: nextDraft.group,
      priority: nextDraft.priority,
      cf: nextDraft.cf,
      explain: nextDraft.explain,
      enabled: nextDraft.enabled,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruleQuery.data, isNew, params.code]);

  const vocabularyItems = vocabulary.data ?? [];

  const currentRule = (): Rule =>
    ruleFromDraft({ ...draft, ...form.values, kind: form.values.kind });

  /** Переход между вкладками: конструктор → YAML сериализует черновик; обратно — разбирает. */
  const switchTab = (next: string) => {
    if (next === tab) return;
    if (next === 'yaml') {
      setYamlText(toYaml(canonicalBody(currentRule())));
      setYamlError(null);
      setTab('yaml');
      return;
    }
    const parsed = parseYaml(yamlText);
    if (!parsed.ok) {
      setYamlError(parsed.error);
      return;
    }
    if (typeof parsed.value !== 'object' || parsed.value === null || Array.isArray(parsed.value)) {
      setYamlError('YAML должен описывать одно правило — объект с полями code, kind, when, …');
      return;
    }
    const body = parsed.value as Record<string, unknown>;
    if ('when' in body && !isConditionNode(body.when)) {
      setYamlError('Поле when не похоже на условие: ожидался {all|any|not|fact|expr|goal}');
      return;
    }
    const nextDraft = draftFromBody(body);
    setDraft(nextDraft);
    form.setValues({
      code: nextDraft.code,
      name: nextDraft.name,
      kind: nextDraft.kind,
      group: nextDraft.group,
      priority: nextDraft.priority,
      cf: nextDraft.cf,
      explain: nextDraft.explain,
      enabled: nextDraft.enabled,
    });
    setYamlError(null);
    setTab('constructor');
  };

  const save = () => {
    setSaveErrors([]);
    let body: Rule;
    if (tab === 'yaml') {
      const parsed = parseYaml(yamlText);
      if (!parsed.ok) {
        setYamlError(parsed.error);
        return;
      }
      if (
        typeof parsed.value !== 'object' ||
        parsed.value === null ||
        Array.isArray(parsed.value)
      ) {
        setYamlError('YAML должен описывать одно правило — объект с полями code, kind, when, …');
        return;
      }
      const checked = ruleBodySchema.safeParse(parsed.value);
      if (!checked.success) {
        setSaveErrors(checked.error.issues.map((issue) => issue.message));
        return;
      }
      body = checked.data as Rule;
      const nextDraft = draftFromBody(parsed.value as Record<string, unknown>);
      setDraft(nextDraft);
      form.setValues({
        code: nextDraft.code,
        name: nextDraft.name,
        kind: nextDraft.kind,
        group: nextDraft.group,
        priority: nextDraft.priority,
        cf: nextDraft.cf,
        explain: nextDraft.explain,
        enabled: nextDraft.enabled,
      });
    } else {
      const metaResult = ruleMetaSchema.safeParse(form.values);
      if (!metaResult.success) {
        setSaveErrors(metaResult.error.issues.map((issue) => issue.message));
        return;
      }
      if (!isConditionNode(draft.when)) {
        setSaveErrors(['Условие when задано некорректно — откройте вкладку YAML и проверьте тело']);
        return;
      }
      body = currentRule();
    }

    const onSuccess = (saved: { code: string; warning?: string | null }) => {
      if (saved.warning) {
        notifications.show({
          color: 'yellow',
          title: 'Сохранено с предупреждением',
          message: saved.warning,
        });
      } else {
        notifications.show({ color: 'green', title: 'Правило сохранено', message: saved.code });
      }
      if (isNew) {
        navigate(`/admin/kb/rules/${saved.code}`, { replace: true });
      }
    };

    if (isNew) {
      createRule.mutate(body, { onSuccess, onError: notifyError });
    } else {
      replaceRule.mutate(body, { onSuccess, onError: notifyError });
    }
  };

  const retire = () => {
    if (!params.code) return;
    retireRule.mutate(params.code, {
      onSuccess: () => {
        notifications.show({
          color: 'green',
          title: 'Правило выведено из эксплуатации',
          message: params.code,
        });
        navigate('/admin/kb/rules');
      },
      onError: (error) => {
        notifyError(error);
        setRetireOpen(false);
      },
    });
  };

  if (!isNew && ruleQuery.isPending) {
    return <QueryState isPending error={ruleQuery.error} />;
  }
  if (!isNew && ruleQuery.error) {
    return <QueryState isPending={false} error={ruleQuery.error} />;
  }

  const saving = createRule.isPending || replaceRule.isPending;
  const hasExpr = treeHasExpr(draft.when);

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          <Group gap="xs" align="center">
            <Title order={3}>{isNew ? 'Новое правило' : params.code}</Title>
            <Badge color={draft.origin === 'generated' ? 'teal' : 'gray'} variant="light">
              {draft.origin === 'generated' ? 'Сгенерировано' : 'Ручное'}
            </Badge>
          </Group>
          <Text size="sm" c="dimmed" mt={2}>
            Коды правил не переиспользуются. Каждое сохранение пишет ревизию в историю.
          </Text>
        </div>
        <Group>
          <Button
            component={Link}
            to="/admin/kb/rules"
            variant="default"
            leftSection={<IconArrowLeft size={16} />}
          >
            К списку
          </Button>
          {!isNew ? (
            <Button
              component={Link}
              to={`/admin/kb/rules/${params.code}/test`}
              variant="light"
              leftSection={<IconTestPipe size={16} />}
            >
              Проверить на примере
            </Button>
          ) : null}
          <Button
            color="green"
            leftSection={<IconDeviceFloppy size={16} />}
            loading={saving}
            onClick={save}
          >
            Сохранить
          </Button>
        </Group>
      </Group>

      {draft.origin === 'generated' && !isNew ? (
        <Alert color="yellow" icon={<IconInfoCircle size={16} />} title="Сгенерированное правило">
          Ручная правка переведёт его в «ручные» (origin: manual, override) — регенерация
          справочников больше не будет его перезаписывать. Обычно правят справочник и запускают
          «Перегенерировать».
        </Alert>
      ) : null}

      {saveErrors.length > 0 ? (
        <Alert color="red" title="Правило не сохранено">
          <Stack gap={2}>
            {saveErrors.map((message) => (
              <Text size="sm" key={message}>
                • {message}
              </Text>
            ))}
          </Stack>
        </Alert>
      ) : null}

      <Tabs value={tab} onChange={(value) => value && switchTab(value)}>
        <Tabs.List>
          <Tabs.Tab value="constructor">Конструктор</Tabs.Tab>
          <Tabs.Tab value="yaml">YAML</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="constructor" pt="md">
          <Stack gap="md">
            {hasExpr ? (
              <Alert color="yellow" icon={<IconInfoCircle size={16} />}>
                В условии есть узел-выражение (expr) — конструктор показывает его только для чтения.
                Для правки таких узлов используйте вкладку «YAML».
              </Alert>
            ) : null}
            <Paper withBorder p="md" radius="md">
              <Stack gap="sm">
                <Text size="sm" fw={500}>
                  Описание
                </Text>
                <Group gap="md" grow wrap="wrap">
                  <TextInput
                    label="Код"
                    placeholder="PREFIX-NNN"
                    disabled={!isNew}
                    {...form.getInputProps('code')}
                  />
                  <TextInput
                    label="Название"
                    placeholder="Что делает правило"
                    {...form.getInputProps('name')}
                  />
                </Group>
                <Group gap="md" grow wrap="wrap">
                  <Select
                    label="Вид"
                    data={KIND_OPTIONS}
                    allowDeselect={false}
                    {...form.getInputProps('kind')}
                  />
                  <TextInput label="Группа" placeholder="budget" {...form.getInputProps('group')} />
                </Group>
                <Group gap="md" grow wrap="wrap">
                  <NumberInput label="Приоритет (salience)" {...form.getInputProps('priority')} />
                  <NumberInput
                    label="Коэффициент уверенности (CF)"
                    step={0.05}
                    min={0}
                    max={1}
                    {...form.getInputProps('cf')}
                  />
                  <Switch
                    label="Включено"
                    mt={24}
                    {...form.getInputProps('enabled', { type: 'checkbox' })}
                  />
                </Group>
                <Textarea
                  label="Объяснение (explain)"
                  placeholder="Почему правило сработало — текст для клиента"
                  autosize
                  minRows={2}
                  {...form.getInputProps('explain')}
                />
                {draft.goal ? (
                  <Text size="sm" c="dimmed">
                    Цель обратного вывода: <code>{JSON.stringify(draft.goal)}</code> — правится в
                    YAML.
                  </Text>
                ) : null}
              </Stack>
            </Paper>

            <div>
              <Text size="sm" fw={500} mb="xs">
                Условие (when)
              </Text>
              {isFactNode(draft.when) || hasExprRootLeaf(draft.when) ? (
                <Stack gap="xs">
                  <ConditionTreeEditor
                    node={draft.when}
                    onChange={(when) => setDraft({ ...draft, when })}
                    vocabulary={vocabularyItems}
                    root
                  />
                  <Button
                    variant="light"
                    size="compact-sm"
                    disabled={vocabularyItems.length === 0}
                    onClick={() => {
                      const fact = vocabularyItems[0];
                      if (!fact) return;
                      const leaf = draft.when as ConditionNode;
                      setDraft({ ...draft, when: { all: [leaf, defaultLeaf(fact)] } });
                    }}
                  >
                    Сделать составным (добавить условие)
                  </Button>
                </Stack>
              ) : (
                <ConditionTreeEditor
                  node={draft.when}
                  onChange={(when) => setDraft({ ...draft, when })}
                  vocabulary={vocabularyItems}
                  root
                />
              )}
            </div>

            <Alert icon={<IconInfoCircle size={16} />} variant="light">
              Действия правила (then) редактируются во вкладке «YAML»: там правится всё тело правила
              целиком, включая assert/reject/prefer и цели goal-правил.
            </Alert>
            <QueryState isPending={vocabulary.isPending} error={vocabulary.error} />
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="yaml" pt="md">
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Полное тело правила в YAML (как в файлах knowledge/rules/). Синтаксис проверяется при
              вводе; при возврате в «Конструктор» дерево условий пересобирается из YAML.
            </Text>
            <CodeEditor
              ariaLabel="Тело правила в YAML"
              language="yaml"
              value={yamlText}
              onChange={(next) => {
                setYamlText(next);
                const parsed = parseYaml(next);
                setYamlError(parsed.ok ? null : parsed.error);
              }}
              height={460}
            />
            {yamlError ? (
              <Alert color="red" title="Ошибка синтаксиса YAML">
                {yamlError}
              </Alert>
            ) : null}
          </Stack>
        </Tabs.Panel>
      </Tabs>

      <Divider />
      <Group justify="space-between">
        <Text size="xs" c="dimmed">
          Тестируется только сохранённый черновик: несохранённые правки сначала сохраните.
        </Text>
        {!isNew ? (
          <Button
            color="red"
            variant="light"
            leftSection={<IconPlayerStop size={16} />}
            onClick={() => setRetireOpen(true)}
          >
            Вывести из эксплуатации
          </Button>
        ) : null}
      </Group>

      <Modal
        opened={retireOpen}
        onClose={() => setRetireOpen(false)}
        title={`Вывести ${params.code ?? ''} из эксплуатации?`}
      >
        <Text size="sm">
          Правило будет выключено (enabled=false) и перестанет попадать в новые снимки базы знаний.
          Код останется занятим: коды правил не переиспользуются. История ревизий сохранится.
        </Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setRetireOpen(false)}>
            Отмена
          </Button>
          <Button color="red" loading={retireRule.isPending} onClick={retire}>
            Вывести из эксплуатации
          </Button>
        </Group>
      </Modal>
    </Stack>
  );
}

/** Корневой узел — лист-выражение или подцель (нужна кнопка составного условия). */
function hasExprRootLeaf(node: ConditionNode): boolean {
  return 'expr' in node || 'goal' in node;
}
