import { vi } from 'vitest';

/**
 * Мок Monaco для jsdom: вместо редактора — textarea с теми же value/onChange.
 * Импортировать первым в тестовых файлах, рендерящих компоненты с CodeEditor.
 */
vi.mock('@monaco-editor/react', () => ({
  loader: { config: vi.fn() },
  default: function EditorMock(props: {
    value?: string;
    onChange?: (value?: string) => void;
    options?: { ariaLabel?: string; readOnly?: boolean };
  }) {
    return (
      <textarea
        aria-label={props.options?.ariaLabel ?? 'monaco'}
        readOnly={props.options?.readOnly}
        value={props.value ?? ''}
        onChange={(event) => props.onChange?.(event.currentTarget.value)}
      />
    );
  },
}));
