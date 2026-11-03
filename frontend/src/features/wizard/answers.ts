import type { QuestionOut, QuestionnaireOut, StepOut } from '../../api/types';

/** Ответы визарда: `{id вопроса: ответ}` в формате API. */
export type Answers = Record<string, unknown>;

export const UNKNOWN = 'unknown';

/** Ответ на вопрос «задачи»: основная задача и дополнительные. */
export interface TasksAnswer {
  main: string | null;
  extra: string[];
}

/** Приводит сохранённый ответ к виду «задачи»; чужой формат даёт пустой ответ. */
export function asTasks(value: unknown): TasksAnswer {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { main: null, extra: [] };
  }
  const { main, extra } = value as Record<string, unknown>;
  return {
    main: typeof main === 'string' ? main : null,
    extra: Array.isArray(extra) ? extra.filter((e): e is string => typeof e === 'string') : [],
  };
}
export const DEFAULT_BUDGET = 100_000;

/** Начальный ответ на вопрос. */
function initialAnswer(question: QuestionOut): unknown {
  switch (question.type) {
    case 'tasks':
      return { main: null, extra: [] } satisfies TasksAnswer;
    case 'number':
      return Math.min(Math.max(DEFAULT_BUDGET, question.min ?? 0), question.max ?? DEFAULT_BUDGET);
    case 'multichoice':
      return [];
    default:
      return UNKNOWN;
  }
}

/** Начальные ответы; `previous` — ответы прошлой консультации (для «Изменить ответы»). */
export function initialAnswers(questionnaire: QuestionnaireOut, previous: Answers = {}): Answers {
  const answers: Answers = {};
  for (const step of questionnaire.steps) {
    for (const question of step.questions) {
      answers[question.id] = previous[question.id] ?? initialAnswer(question);
    }
  }
  return answers;
}

/** Ошибка заполнения шага или `null`, если всё в порядке. */
export function stepError(step: StepOut, answers: Answers): string | null {
  for (const question of step.questions) {
    const answer = answers[question.id];
    if (question.type === 'tasks' && asTasks(answer).main === null) {
      return 'Выберите основную задачу';
    }
    if (question.type === 'number') {
      const low = question.min ?? 0;
      const high = question.max ?? Number.MAX_SAFE_INTEGER;
      if (typeof answer !== 'number' || answer < low || answer > high) {
        return `${question.title}: допустимо от ${low} до ${high}`;
      }
    }
  }
  return null;
}
