import { Button, Group, Modal, Select, Stack, Text } from '@mantine/core';
import { IconArrowsExchange } from '@tabler/icons-react';
import { useState } from 'react';

import type { BuildItemOut, Category } from '../../api/types';
import { formatRub } from '../../lib/format';
import { CATEGORY_TITLES } from '../../lib/labels';
import { useApplyEdit } from './useApplyEdit';

interface RedistributeButtonProps {
  buildId: string;
  items: BuildItemOut[];
}

function asCategory(value: string | null, items: BuildItemOut[]): Category | null {
  return items.find((item) => item.category === value)?.category ?? null;
}

/** «Перераспределить средства»: сэкономить на одной детали и вложить разницу в другую. */
export function RedistributeButton({ buildId, items }: RedistributeButtonProps) {
  const { apply, isPending } = useApplyEdit(buildId);
  const [opened, setOpened] = useState(false);
  const [from, setFrom] = useState<Category | null>(null);
  const [to, setTo] = useState<Category | null>(null);
  const editable = items.filter((item) => !item.owned);
  const options = editable.map((item) => ({
    value: item.category,
    label: `${CATEGORY_TITLES[item.category]} — ${formatRub(item.price_kop)}`,
  }));
  const ready = from !== null && to !== null && from !== to;

  return (
    <>
      <Button
        variant="light"
        leftSection={<IconArrowsExchange size={16} />}
        onClick={() => setOpened(true)}
        disabled={editable.length < 2}
      >
        Перераспределить средства
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Перераспределить средства">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Система возьмёт в первой категории деталь дешевле нынешней и на сэкономленные деньги —
            деталь лучше во второй. Остальные детали по возможности не меняются; если новой детали
            нужен, например, блок питания мощнее, подберётся и он. Бюджет прежний.
          </Text>
          <Select
            label="Сэкономить на"
            data={options}
            value={from}
            onChange={(value) => setFrom(asCategory(value, editable))}
          />
          <Select
            label="Вложить в"
            data={options.filter((option) => option.value !== from)}
            value={to}
            onChange={(value) => setTo(asCategory(value, editable))}
          />
          <Group justify="flex-end">
            <Button
              disabled={!ready}
              loading={isPending}
              onClick={() =>
                ready &&
                apply({ kind: 'shift_budget', category: from, to_category: to }, () =>
                  setOpened(false),
                )
              }
            >
              Пересобрать
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
