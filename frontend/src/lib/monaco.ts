/**
 * Настройка Monaco для редакторов админки (режимы JSON/YAML): редактор и воркеры
 * собираются Vite из node_modules, без обращений к CDN (ADR 0010, п. 10).
 */
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
// Пути через exports-мап пакета (0.57): "./*" → "./esm/vs/*.js",
// поэтому без префикса "esm/vs/" — иначе резолв падает (vite: "Does the file exist?").
import editorWorker from 'monaco-editor/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/language/json/json.worker?worker';

self.MonacoEnvironment = {
  getWorker(_workerId: string, label: string): Worker {
    if (label === 'json') return new jsonWorker();
    return new editorWorker();
  },
};

loader.config({ monaco });

export { monaco };
