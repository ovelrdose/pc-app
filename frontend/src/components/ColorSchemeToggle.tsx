import { SegmentedControl, useMantineColorScheme, type MantineColorScheme } from '@mantine/core';

const options: { value: MantineColorScheme; label: string }[] = [
  { value: 'light', label: 'Светлая' },
  { value: 'auto', label: 'Авто' },
  { value: 'dark', label: 'Тёмная' },
];

function isColorScheme(value: string): value is MantineColorScheme {
  return options.some((option) => option.value === value);
}

export function ColorSchemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();

  return (
    <SegmentedControl
      size="xs"
      aria-label="Тема оформления"
      value={colorScheme}
      data={options}
      onChange={(value) => {
        if (isColorScheme(value)) setColorScheme(value);
      }}
    />
  );
}
