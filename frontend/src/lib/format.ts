const rubFormatter = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

const rubWithKopFormatter = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const decimalFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

/** Форматирует сумму в копейках как рубли: 12599000 → «125 990 ₽». */
export function formatRub(kop: number): string {
  if (!Number.isSafeInteger(kop)) {
    throw new RangeError(`Сумма в копейках должна быть целым числом: ${kop}`);
  }
  const formatter = kop % 100 === 0 ? rubFormatter : rubWithKopFormatter;
  return formatter.format(kop / 100);
}

/** Целые рубли: 170000 → «170 000 ₽». */
export function formatRubles(rub: number): string {
  return rubFormatter.format(rub);
}

/** Разница в копейках со знаком: −1650000 → «−16 500 ₽», 0 → «0 ₽». */
export function formatRubDelta(kop: number): string {
  const sign = kop > 0 ? '+' : kop < 0 ? '−' : '';
  return sign + formatRub(Math.abs(kop));
}

/** Число с разрядами, как суммы: 1500 → «1 500», 2.5 → «2,5». */
export function formatNumber(value: number): string {
  const [whole = '', fraction] = (Math.round(value * 10) / 10).toString().split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
  return fraction ? `${grouped},${fraction}` : grouped;
}

/** FPS: 105.3 → «≈ 105». */
export function formatFps(fps: number): string {
  return `≈ ${Math.round(fps)}`;
}

/** Минуты: 6.43 → «6,4 мин». */
export function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes)) return '—';
  return `${decimalFormatter.format(minutes)} мин`;
}

/** Процент со знаком: 3.25 → «+3,3%», −31.8 → «−31,8%». */
export function formatPercent(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${decimalFormatter.format(Math.abs(value))}%`;
}

/** Доля 0…1 как процент: 0.959 → «96%». */
export function formatShare(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Дата и время: «29.10.2026, 14:30». */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
