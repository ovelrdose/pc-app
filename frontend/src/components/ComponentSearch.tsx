import { Combobox, Loader, ScrollArea, TextInput, useCombobox } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';

import type { Category, ComponentOut } from '../api/types';
import { formatRub } from '../lib/format';
import { CATEGORY_TITLES } from '../lib/labels';
import { useComponentSearch } from '../lib/useComponentSearch';

interface ComponentSearchProps {
  label: string;
  placeholder?: string;
  category?: Category;
  onSelect: (component: ComponentOut) => void;
}

/** Поле поиска по каталогу с выпадающим списком товаров. */
export function ComponentSearch({ label, placeholder, category, onSelect }: ComponentSearchProps) {
  const [text, setText] = useState('');
  const combobox = useCombobox();
  const search = useComponentSearch(text, category);
  const items = search.data ?? [];

  return (
    <Combobox
      onOptionSubmit={(id) => {
        const found = items.find((item) => item.id === id);
        if (found) onSelect(found);
        setText('');
        combobox.closeDropdown();
      }}
      store={combobox}
    >
      <Combobox.Target>
        <TextInput
          label={label}
          placeholder={placeholder ?? 'Название или артикул, от 2 символов'}
          leftSection={<IconSearch size={16} />}
          rightSection={search.isFetching ? <Loader size="xs" /> : null}
          value={text}
          onChange={(event) => {
            setText(event.currentTarget.value);
            combobox.openDropdown();
          }}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => combobox.closeDropdown()}
        />
      </Combobox.Target>
      <Combobox.Dropdown hidden={text.trim().length < 2}>
        <Combobox.Options>
          <ScrollArea.Autosize mah={300} type="scroll">
            {items.length === 0 ? (
              <Combobox.Empty>{search.isFetching ? 'Ищем…' : 'Ничего не найдено'}</Combobox.Empty>
            ) : (
              items.map((item) => (
                <Combobox.Option value={item.id} key={item.id}>
                  {item.name} · {CATEGORY_TITLES[item.category]} · {formatRub(item.price_kop)}
                </Combobox.Option>
              ))
            )}
          </ScrollArea.Autosize>
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}
