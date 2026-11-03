import { useSearchParams } from 'react-router-dom';

import type { ConsultationOut } from '../../api/types';
import { QueryState } from '../../components/QueryState';
import { useConsultation } from '../results/api';
import { useQuestionnaire } from './api';
import type { OwnedPart } from './OwnedPartsStep';
import { WizardForm } from './WizardForm';

/** Имеющиеся детали прошлой консультации. */
function ownedParts(consultation: ConsultationOut | undefined): OwnedPart[] {
  return (consultation?.owned ?? []).map((item) => ({
    id: item.component_id,
    category: item.category,
    name: item.name,
    price_kop: item.price_kop,
  }));
}

/** Мастер подбора: анкета по шагам и запуск подбора. */
export function WizardPage() {
  const [params] = useSearchParams();
  const fromId = params.get('from');
  const questionnaire = useQuestionnaire();
  const previous = useConsultation(fromId ?? undefined);

  const waiting = questionnaire.isPending || (fromId !== null && previous.isPending);
  if (waiting || questionnaire.error || previous.error) {
    return (
      <QueryState isPending={waiting} error={questionnaire.error ?? (fromId && previous.error)} />
    );
  }
  return (
    <WizardForm
      key={fromId ?? 'new'}
      questionnaire={questionnaire.data}
      previousAnswers={previous.data?.answers}
      previousOwned={ownedParts(previous.data)}
    />
  );
}
