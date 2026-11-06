import { NavLink, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

import { QueryState } from '../../components/QueryState';
import { useReferenceList } from './api';
import { ReferenceEditor } from './ReferenceEditor';
import { REFERENCE_TITLES, TABLE_REFERENCE_NAMES } from './referenceLabels';

const NAME_ORDER = [...TABLE_REFERENCE_NAMES, 'questionnaire', 'golden'];

function titleFor(name: string): string {
  return REFERENCE_TITLES[name] ?? name;
}

function orderedNames(names: string[]): string[] {
  const known = NAME_ORDER.filter((name) => names.includes(name));
  const rest = names.filter((name) => !NAME_ORDER.includes(name)).sort();
  return [...known, ...rest];
}

/** Справочники, анкета и эталонные кейсы: список имён слева, редактор выбранного справа. */
export function ReferencePage() {
  const list = useReferenceList();
  const [selected, setSelected] = useState<string | null>(null);

  const names = useMemo(() => orderedNames(Object.keys(list.data ?? {})), [list.data]);

  // Первый справочник выбираем автоматически.
  useEffect(() => {
    if (selected === null && names.length > 0) {
      setSelected(names[0] ?? null);
    }
  }, [names, selected]);

  return (
    <Stack gap="md">
      <div>
        <Title order={3}>Справочники и анкета</Title>
        <Text size="sm" c="dimmed">
          Табличные справочники — источник сгенерированных правил GEN-*: правьте таблицу, сохраните
          и запустите «Перегенерировать». Анкета задаёт вопросы визарда, golden — эталонные кейсы
          проверки.
        </Text>
      </div>

      <QueryState isPending={list.isPending} error={list.error} />
      {names.length > 0 ? (
        <SimpleGrid cols={{ base: 1, md: 4 }} spacing="md">
          <Paper withBorder radius="md" p={4}>
            <Stack gap={2}>
              {names.map((name) => (
                <NavLink
                  key={name}
                  label={titleFor(name)}
                  description={name}
                  active={selected === name}
                  onClick={() => setSelected(name)}
                />
              ))}
            </Stack>
          </Paper>
          <div style={{ gridColumn: 'span 3' }}>
            {selected ? <ReferenceEditor name={selected} /> : null}
          </div>
        </SimpleGrid>
      ) : null}
    </Stack>
  );
}
