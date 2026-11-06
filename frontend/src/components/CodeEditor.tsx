import Editor from '@monaco-editor/react';
import type { OnChange } from '@monaco-editor/react';

/** Настройка Monaco (воркеры из node_modules, без CDN) подключается один раз в точке входа (`main.tsx`). */

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  language: 'yaml' | 'json';
  /** Высота редактора, по умолчанию 320. */
  height?: number;
  /** Подпись для скринридеров. */
  ariaLabel: string;
  readOnly?: boolean;
}

/** Текстовый редактор кода (YAML/JSON) на Monaco — переиспользуется в админке знаний. */
export function CodeEditor({
  value,
  onChange,
  language,
  height = 320,
  ariaLabel,
  readOnly = false,
}: CodeEditorProps) {
  const handleChange: OnChange = (next) => {
    onChange(next ?? '');
  };

  return (
    <div aria-label={ariaLabel}>
      <Editor
        height={height}
        language={language}
        value={value}
        onChange={handleChange}
        options={{
          minimap: { enabled: false },
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          tabSize: 2,
          readOnly,
          ariaLabel,
        }}
      />
    </div>
  );
}
