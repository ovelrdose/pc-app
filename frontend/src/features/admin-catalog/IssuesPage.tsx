import {
  Anchor,
  Button,
  Group,
  List,
  Pagination,
  Select,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { Category, ComponentStatus } from '../../api/types';
import { CATEGORY_TITLES, CATEGORY_ORDER } from '../../lib/labels';
import { formatRub } from '../../lib/format';
import { QueryState } from '../../components/QueryState';
import { PAGE_SIZE, useAdminComponents, useCatalogIssues } from './api';
import { StatusBadge } from './StatusBadge';
import { STATUS_TITLES } from './labels';

const STATUS_FILTER_OPTIONS: { value: ComponentStatus; label: string }[] = [
  { value: 'incomplete', label: STATUS_TITLES.incomplete },
  { value: 'needs_kb', label: STATUS_TITLES.needs_kb },
];

/**
 * «Требуют внимания»: позиции со статусами «неполный» и «требует знаний» с причинами.
 * Без фильтра статуса список берётся из `GET /admin/catalog/issues`; с фильтром — из
 * общего списка админки (там фильтр по статусу), чтобы пагинация оставалась корректной.
 */
export function IssuesPage() {
  const [category, setCategory] = useState<Category | null>(null);
  const [status, setStatus] = useState<ComponentStatus | null>(null);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);

  const issuesFilters = { category, q, page };
  const componentsFilters = {
    category,
    brand: '',
    status,
    source: null,
    q,
    priceStaleDays: false,
    page,
  };
  const issues = useCatalogIssues(issuesFilters, status === null);
  const filtered = useAdminComponents(componentsFilters, status !== null);
  const query = status === null ? issues : filtered;

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  return (
    <>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={3}>Требуют внимания</Title>
          <Text size="sm" c="dimmed">
            Позиции со статусами «неполный» и «требует знаний» и причинами. Когда данные заполнены
            или справочник опубликован, статус станет «активен» сам.
          </Text>
        </div>
      </Group>

      <Group mt="md" gap="sm" wrap="wrap" align="flex-end">
        <Select
          label="Статус"
          placeholder="Все проблемные"
          clearable
          w={200}
          data={STATUS_FILTER_OPTIONS}
          value={status}
          onChange={(value) => {
            setStatus((value as ComponentStatus | null) ?? null);
            setPage(1);
          }}
        />
        <Select
          label="Категория"
          placeholder="Все"
          clearable
          w={180}
          data={CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_TITLES[value] }))}
          value={category}
          onChange={(value) => {
            setCategory((value as Category | null) ?? null);
            setPage(1);
          }}
        />
        <TextInput
          label="Поиск"
          placeholder="название или артикул"
          w={220}
          leftSection={<IconSearch size={16} />}
          value={q}
          onChange={(event) => {
            setQ(event.currentTarget.value);
            setPage(1);
          }}
        />
      </Group>

      <QueryState isPending={query.isPending} error={query.error} />
      {!query.isPending && !query.error && items.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          Проблемных позиций нет — каталог полностью активен.
        </Text>
      ) : null}
      {items.length > 0 ? (
        <>
          <Table striped highlightOnHover verticalSpacing="sm" mt="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Название</Table.Th>
                <Table.Th>Категория</Table.Th>
                <Table.Th>Цена</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th>Причины</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((component) => (
                <Table.Tr key={component.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/admin/catalog/${component.id}`} fw={500}>
                      {component.name}
                    </Anchor>
                    <Text size="xs" c="dimmed">
                      {component.sku}
                    </Text>
                  </Table.Td>
                  <Table.Td>{CATEGORY_TITLES[component.category]}</Table.Td>
                  <Table.Td>{formatRub(component.price_kop)}</Table.Td>
                  <Table.Td>
                    <StatusBadge status={component.status} issues={component.status_issues} />
                  </Table.Td>
                  <Table.Td>
                    {component.status_issues.length > 0 ? (
                      <List size="sm" spacing={2}>
                        {component.status_issues.map((issue) => (
                          <List.Item key={issue}>{issue}</List.Item>
                        ))}
                      </List>
                    ) : (
                      <Text size="sm" c="dimmed">
                        —
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Button
                      component={Link}
                      to={`/admin/catalog/${component.id}`}
                      variant="light"
                      size="compact-sm"
                    >
                      Редактировать
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Group justify="center" mt="md">
            <Pagination
              total={Math.max(1, Math.ceil(total / PAGE_SIZE))}
              value={page}
              onChange={setPage}
            />
          </Group>
        </>
      ) : null}
    </>
  );
}
