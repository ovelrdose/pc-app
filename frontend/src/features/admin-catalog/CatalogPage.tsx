import { Button, Group, Pagination, Select, Switch, Text, TextInput, Title } from '@mantine/core';
import {
  IconDownload,
  IconFileUpload,
  IconPlus,
  IconSearch,
  IconAlertTriangle,
} from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { Category, ComponentOut, ComponentStatus } from '../../api/types';
import { CATEGORY_TITLES, CATEGORY_ORDER } from '../../lib/labels';
import { notifyError } from '../../lib/notify';
import { QueryState } from '../../components/QueryState';
import { downloadCatalogExport, PAGE_SIZE, useAdminComponents, usePatchComponent } from './api';
import { ComponentsTable } from './ComponentsTable';
import { STATUS_TITLES } from './labels';

const SOURCE_OPTIONS = [
  { value: 'manual', label: 'Вручную' },
  { value: 'import', label: 'Импорт' },
];

/** Админка каталога: таблица с фильтрами, создание, импорт/экспорт, «требуют внимания». */
export function CatalogPage() {
  const [category, setCategory] = useState<Category | null>(null);
  const [brand, setBrand] = useState('');
  const [status, setStatus] = useState<ComponentStatus | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [priceStaleDays, setPriceStaleDays] = useState(false);
  const [page, setPage] = useState(1);

  const filters = {
    category,
    brand,
    status,
    source: (source as 'manual' | 'import' | null) ?? null,
    q,
    priceStaleDays,
    page,
  };
  const components = useAdminComponents(filters);
  const patch = usePatchComponent();
  const [exporting, setExporting] = useState(false);

  const items: ComponentOut[] = components.data?.items ?? [];
  const total = components.data?.total ?? 0;

  const toggleStock = (component: ComponentOut, inStock: boolean) => {
    patch.mutate({ id: component.id, patch: { in_stock: inStock } }, { onError: notifyError });
  };

  const changeStatus = (component: ComponentOut, next: ComponentStatus) => {
    patch.mutate({ id: component.id, patch: { status: next } }, { onError: notifyError });
  };

  const exportZip = async () => {
    setExporting(true);
    try {
      await downloadCatalogExport();
    } catch (error) {
      notifyError(error);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={3}>Каталог</Title>
          <Text size="sm" c="dimmed">
            {total > 0 ? `Позиций: ${total}` : 'Комплектующие магазина'}
          </Text>
        </div>
        <Group>
          <Button
            component={Link}
            to="/admin/catalog/issues"
            variant="light"
            color="orange"
            leftSection={<IconAlertTriangle size={16} />}
          >
            Требуют внимания
          </Button>
          <Button
            component={Link}
            to="/admin/catalog/import"
            variant="light"
            leftSection={<IconFileUpload size={16} />}
          >
            Импорт CSV
          </Button>
          <Button
            variant="light"
            leftSection={<IconDownload size={16} />}
            loading={exporting}
            onClick={() => void exportZip()}
          >
            Экспорт zip
          </Button>
          <Button component={Link} to="/admin/catalog/new" leftSection={<IconPlus size={16} />}>
            Создать
          </Button>
        </Group>
      </Group>

      <Group mt="md" gap="sm" wrap="wrap" align="flex-end">
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
          label="Бренд"
          placeholder="например, AMD"
          w={160}
          value={brand}
          onChange={(event) => {
            setBrand(event.currentTarget.value);
            setPage(1);
          }}
        />
        <Select
          label="Статус"
          placeholder="Все"
          clearable
          w={170}
          data={(Object.keys(STATUS_TITLES) as ComponentStatus[]).map((value) => ({
            value,
            label: STATUS_TITLES[value],
          }))}
          value={status}
          onChange={(value) => {
            setStatus((value as ComponentStatus | null) ?? null);
            setPage(1);
          }}
        />
        <Select
          label="Источник"
          placeholder="Все"
          clearable
          w={140}
          data={SOURCE_OPTIONS}
          value={source}
          onChange={(value) => {
            setSource(value);
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
        <Switch
          label="Цена не проверялась > 30 дней"
          checked={priceStaleDays}
          onChange={(event) => {
            setPriceStaleDays(event.currentTarget.checked);
            setPage(1);
          }}
        />
      </Group>

      <QueryState isPending={components.isPending} error={components.error} />
      {!components.isPending && !components.error && items.length === 0 ? (
        <Text c="dimmed" ta="center" py="xl">
          По заданным фильтрам ничего не найдено. Измените фильтры или создайте компонент.
        </Text>
      ) : null}
      {items.length > 0 ? (
        <>
          <ComponentsTable
            items={items}
            onToggleStock={toggleStock}
            onChangeStatus={changeStatus}
            busy={patch.isPending}
          />
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
