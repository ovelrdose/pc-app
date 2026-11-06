import {
  Alert,
  Button,
  Group,
  Modal,
  Pagination,
  Select,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconInfoCircle, IconPlus, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';

import type { RuleKind, RuleOrigin, RuleOut } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { PAGE_SIZE, useRules } from './api';
import { RULE_KIND_TITLES, RULE_ORIGIN_TITLES } from './labels';
import { RulesTable } from './RulesTable';

/** Список правил рабочей копии: фильтры по группе/виду/происхождению/статусу, пагинация. */
export function RulesPage() {
  const navigate = useNavigate();
  const [group, setGroup] = useState('');
  const [kind, setKind] = useState<RuleKind | null>(null);
  const [origin, setOrigin] = useState<RuleOrigin | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [overrideTarget, setOverrideTarget] = useState<RuleOut | null>(null);

  const filters = { group, kind, origin, enabled, q, page };
  const rules = useRules(filters);

  const items = rules.data?.items ?? [];
  const total = rules.data?.total ?? 0;

  /** Сгенерированные правила правятся через справочники — редактирование = override. */
  const editRule = (rule: RuleOut) => {
    if (rule.origin === 'generated') {
      setOverrideTarget(rule);
      return;
    }
    navigate(`/admin/kb/rules/${rule.code}`);
  };

  return (
    <>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={3}>Правила базы знаний</Title>
          <Text size="sm" c="dimmed">
            {total > 0 ? `Правил: ${total}` : 'Рабочая копия правил'}
          </Text>
        </div>
        <Button component={Link} to="/admin/kb/rules/new" leftSection={<IconPlus size={16} />}>
          Новое правило
        </Button>
      </Group>

      <Alert icon={<IconInfoCircle size={16} />} variant="light" mt="md">
        Сгенерированные правила (GEN-*) правятся через справочники: отредактируйте таблицу в разделе
        «Справочники» и нажмите «Перегенерировать». Ручная правка сгенерированного правила переведёт
        его в «ручные» (override) — генератор его больше не перезапишет.
      </Alert>

      <Group mt="md" gap="sm" wrap="wrap" align="flex-end">
        <TextInput
          label="Группа"
          placeholder="например, budget"
          w={170}
          value={group}
          onChange={(event) => {
            setGroup(event.currentTarget.value);
            setPage(1);
          }}
        />
        <Select
          label="Вид"
          placeholder="Все"
          clearable
          w={170}
          data={(Object.keys(RULE_KIND_TITLES) as RuleKind[]).map((value) => ({
            value,
            label: RULE_KIND_TITLES[value],
          }))}
          value={kind}
          onChange={(value) => {
            setKind((value as RuleKind | null) ?? null);
            setPage(1);
          }}
        />
        <Select
          label="Происхождение"
          placeholder="Все"
          clearable
          w={170}
          data={(Object.keys(RULE_ORIGIN_TITLES) as RuleOrigin[]).map((value) => ({
            value,
            label: RULE_ORIGIN_TITLES[value],
          }))}
          value={origin}
          onChange={(value) => {
            setOrigin((value as RuleOrigin | null) ?? null);
            setPage(1);
          }}
        />
        <Select
          label="Статус"
          placeholder="Все"
          clearable
          w={150}
          data={[
            { value: 'true', label: 'Включено' },
            { value: 'false', label: 'Выведено' },
          ]}
          value={enabled === null ? null : String(enabled)}
          onChange={(value) => {
            setEnabled(value === null ? null : value === 'true');
            setPage(1);
          }}
        />
        <TextInput
          label="Поиск"
          placeholder="код или название"
          w={220}
          leftSection={<IconSearch size={16} />}
          value={q}
          onChange={(event) => {
            setQ(event.currentTarget.value);
            setPage(1);
          }}
        />
      </Group>

      <QueryState isPending={rules.isPending} error={rules.error} />
      {!rules.isPending && !rules.error && items.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          По заданным фильтрам правил не найдено. Измените фильтры или создайте правило.
        </Text>
      ) : null}
      {items.length > 0 ? (
        <>
          <RulesTable items={items} onEdit={editRule} />
          <Group justify="center" mt="md">
            <Pagination
              total={Math.max(1, Math.ceil(total / PAGE_SIZE))}
              value={page}
              onChange={setPage}
            />
          </Group>
        </>
      ) : null}

      <Modal
        opened={overrideTarget !== null}
        onClose={() => setOverrideTarget(null)}
        title={`Правка ${overrideTarget?.code ?? ''}`}
      >
        <Text size="sm">
          Правило <b>{overrideTarget?.code}</b> сгенерировано из справочника{' '}
          {overrideTarget?.source ? `(${overrideTarget.source})` : ''}. Ручная правка переведёт его
          в «ручные» (override): генератор больше не будет его перезаписывать при регенерации.
        </Text>
        <Text size="sm" c="dimmed" mt="xs">
          Обычно правильнее поправить справочник и нажать «Перегенерировать» в разделе
          «Справочники».
        </Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setOverrideTarget(null)}>
            Отмена
          </Button>
          <Button
            color="orange"
            onClick={() => {
              if (overrideTarget) {
                navigate(`/admin/kb/rules/${overrideTarget.code}`);
              }
              setOverrideTarget(null);
            }}
          >
            Продолжить правку (override)
          </Button>
        </Group>
      </Modal>
    </>
  );
}
