import { ActionIcon, Menu } from '@mantine/core';
import {
  IconArrowDown,
  IconArrowUp,
  IconBan,
  IconDots,
  IconLock,
  IconLockOpen,
  IconReplace,
} from '@tabler/icons-react';

import type { BuildItemOut, ModificationRequest } from '../../api/types';

interface ComponentActionsProps {
  item: BuildItemOut;
  disabled: boolean;
  onEdit: (request: ModificationRequest) => void;
  onAlternatives: () => void;
}

/** Меню правок детали: дешевле, дороже, закрепить, заменить, исключить. */
export function ComponentActions({
  item,
  disabled,
  onEdit,
  onAlternatives,
}: ComponentActionsProps) {
  const { category } = item;
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <ActionIcon
          variant="subtle"
          color="gray"
          aria-label={`Действия: ${item.name}`}
          disabled={disabled}
        >
          <IconDots size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconReplace size={16} />} onClick={onAlternatives}>
          Подобрать замену…
        </Menu.Item>
        <Menu.Item
          leftSection={<IconArrowDown size={16} />}
          onClick={() => onEdit({ kind: 'cheaper', category })}
        >
          Дешевле
        </Menu.Item>
        <Menu.Item
          leftSection={<IconArrowUp size={16} />}
          onClick={() => onEdit({ kind: 'pricier', category })}
        >
          Дороже
        </Menu.Item>
        {item.locked ? (
          <Menu.Item
            leftSection={<IconLockOpen size={16} />}
            onClick={() => onEdit({ kind: 'unlock', category })}
          >
            Открепить
          </Menu.Item>
        ) : (
          <Menu.Item
            leftSection={<IconLock size={16} />}
            onClick={() => onEdit({ kind: 'lock', category })}
          >
            Закрепить (не менять при правках)
          </Menu.Item>
        )}
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<IconBan size={16} />}
          onClick={() => onEdit({ kind: 'exclude_sku', component_id: item.component_id })}
        >
          Исключить этот товар
        </Menu.Item>
        <Menu.Item
          color="red"
          leftSection={<IconBan size={16} />}
          onClick={() => onEdit({ kind: 'exclude_brand', brand: item.brand })}
        >
          Исключить бренд {item.brand}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
