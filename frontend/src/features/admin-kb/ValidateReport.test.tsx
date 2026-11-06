import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../../tests/renderWithProviders';
import { ValidateReport } from './ValidateReport';
import { validateReportFixture } from './testing/fixtures';

describe('ValidateReport', () => {
  it('показывает ошибки, предупреждения и упавшие эталонные кейсы', () => {
    renderWithProviders(<ValidateReport report={validateReportFixture} />);

    expect(screen.getByText(/Ошибки \(2\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/CMP-012: слот `lenght_mm` не существует во фрейме «Видеокарта»/),
    ).toBeInTheDocument();
    expect(screen.getByText(/BUD-031: цикл PRF-011/)).toBeInTheDocument();
    expect(screen.getByText(/Предупреждения \(1\)/)).toBeInTheDocument();
    expect(screen.getByText('SCR-012 дублирует SCR-004')).toBeInTheDocument();
    expect(screen.getByText(/Эталонные кейсы: 15 из 16 прошли/)).toBeInTheDocument();
    expect(screen.getByText(/G-012:/)).toBeInTheDocument();
    expect(screen.getByText(/превышен бюджет на 2 400 ₽/)).toBeInTheDocument();
  });

  it('зелёный итог, когда ошибок нет', () => {
    renderWithProviders(
      <ValidateReport report={{ ...validateReportFixture, errors: [], warnings: [] }} />,
    );
    expect(screen.getByText(/Ошибок нет/)).toBeInTheDocument();
  });
});
