import { Alert, Button, Group, Stack, Stepper, Text, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { QuestionnaireOut } from '../../api/types';
import { notifyError } from '../../lib/notify';
import { useStartConsultation } from './api';
import { initialAnswers, stepError, type Answers } from './answers';
import { OwnedPartsStep, type OwnedPart } from './OwnedPartsStep';
import { QuestionField } from './QuestionField';

interface WizardFormProps {
  questionnaire: QuestionnaireOut;
  previousAnswers?: Answers;
  previousOwned: OwnedPart[];
}

/** Шаги анкеты, проверка ответов и запуск подбора. */
export function WizardForm({ questionnaire, previousAnswers, previousOwned }: WizardFormProps) {
  const navigate = useNavigate();
  const start = useStartConsultation();
  const [active, setActive] = useState(0);
  const [answers, setAnswers] = useState<Answers>(() =>
    initialAnswers(questionnaire, previousAnswers),
  );
  const [owned, setOwned] = useState<OwnedPart[]>(previousOwned);
  const [error, setError] = useState<string | null>(null);

  const steps = questionnaire.steps;
  const ownedIndex = steps.length;
  const isLast = active === ownedIndex;

  const next = () => {
    const current = steps[active];
    const problem = current ? stepError(current, answers) : null;
    setError(problem);
    if (problem) return;
    if (!isLast) {
      setActive(active + 1);
      return;
    }
    start.mutate(
      { answers, ownedComponentIds: owned.map((part) => part.id) },
      {
        onSuccess: (consultation) => navigate(`/consultations/${consultation.id}`),
        onError: notifyError,
      },
    );
  };

  const goTo = (index: number) => {
    // Вперёд — только через проверку шагов кнопкой «Далее».
    if (index < active) {
      setError(null);
      setActive(index);
    }
  };

  return (
    <Stack gap="lg" py="md">
      <Title order={2}>Подбор компьютера</Title>
      <Stepper active={active} onStepClick={goTo} size="sm" allowNextStepsSelect={false}>
        {steps.map((step) => (
          <Stepper.Step key={step.id} label={step.title}>
            <Stack gap="xl" pt="md">
              {step.questions.map((question) => (
                <QuestionField
                  key={question.id}
                  question={question}
                  value={answers[question.id]}
                  onChange={(value) => setAnswers((prev) => ({ ...prev, [question.id]: value }))}
                />
              ))}
            </Stack>
          </Stepper.Step>
        ))}
        <Stepper.Step label="Что уже есть">
          <Stack pt="md">
            <OwnedPartsStep owned={owned} onChange={setOwned} />
          </Stack>
        </Stepper.Step>
      </Stepper>

      {error && (
        <Alert color="orange" icon={<IconInfoCircle />}>
          {error}
        </Alert>
      )}

      <Group justify="space-between">
        <Button variant="default" disabled={active === 0} onClick={() => goTo(active - 1)}>
          Назад
        </Button>
        <Group gap="sm">
          {isLast && start.isPending && (
            <Text size="sm" c="dimmed">
              Подбираем три варианта…
            </Text>
          )}
          <Button onClick={next} loading={start.isPending}>
            {isLast ? 'Подобрать сборки' : 'Далее'}
          </Button>
        </Group>
      </Group>
    </Stack>
  );
}
