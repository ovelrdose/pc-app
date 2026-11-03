import type { QuestionOut } from '../../api/types';
import { ChoiceQuestion } from './ChoiceQuestion';
import { MultiChoiceQuestion } from './MultiChoiceQuestion';
import { NumberQuestion } from './NumberQuestion';
import { TasksQuestion } from './TasksQuestion';
import { YesNoQuestion } from './YesNoQuestion';

interface QuestionFieldProps {
  question: QuestionOut;
  value: unknown;
  onChange: (value: unknown) => void;
}

/** Поле вопроса анкеты по его виду. */
export function QuestionField({ question, value, onChange }: QuestionFieldProps) {
  switch (question.type) {
    case 'tasks':
      return <TasksQuestion question={question} value={value} onChange={onChange} />;
    case 'number':
      return <NumberQuestion question={question} value={value} onChange={onChange} />;
    case 'choice':
      return <ChoiceQuestion question={question} value={value} onChange={onChange} />;
    case 'multichoice':
      return <MultiChoiceQuestion question={question} value={value} onChange={onChange} />;
    case 'yesno':
      return <YesNoQuestion question={question} value={value} onChange={onChange} />;
    default:
      return null;
  }
}
