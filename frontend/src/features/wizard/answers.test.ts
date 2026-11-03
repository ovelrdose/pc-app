import { describe, expect, it } from 'vitest';

import { questionnaire } from '../../../tests/fixtures';
import { asTasks, initialAnswers, stepError } from './answers';

describe('ответы визарда', () => {
  it('начальные значения по видам вопросов и подстановка прошлых ответов', () => {
    expect(initialAnswers(questionnaire)).toEqual({
      tasks: { main: null, extra: [] },
      budget: 100000,
      resolution: 'unknown',
      wifi: 'unknown',
    });
    expect(initialAnswers(questionnaire, { budget: 70000 }).budget).toBe(70000);
  });

  it('ответы прошлого формата (слайдеры) не подставляются', () => {
    const answers = initialAnswers(questionnaire, { purposes: { office: 30 } });
    expect(answers.tasks).toEqual({ main: null, extra: [] });
    expect('purposes' in answers).toBe(false);
    expect(asTasks({ office: 30 })).toEqual({ main: null, extra: [] });
    expect(asTasks(['office'])).toEqual({ main: null, extra: [] });
    expect(asTasks({ main: 'office', extra: ['esports', 1] })).toEqual({
      main: 'office',
      extra: ['esports'],
    });
  });

  it('проверяет шаги: основная задача выбрана и бюджет в диапазоне', () => {
    const [purposes, budget] = questionnaire.steps;
    if (!purposes || !budget) throw new Error('нет шагов');
    const answers = initialAnswers(questionnaire);
    expect(stepError(purposes, answers)).toBe('Выберите основную задачу');
    expect(stepError(purposes, { ...answers, tasks: { main: 'office', extra: [] } })).toBeNull();
    expect(stepError(budget, { ...answers, budget: 1000 })).toMatch(/допустимо/);
    expect(stepError(budget, answers)).toBeNull();
  });
});
