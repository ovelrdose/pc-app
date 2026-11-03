import { describe, expect, it } from 'vitest';

import {
  formatFps,
  formatMinutes,
  formatNumber,
  formatPercent,
  formatRub,
  formatRubDelta,
  formatRubles,
  formatShare,
} from './format';

// Intl использует неразрывные пробелы; для сравнения приводим их к обычным.
const normalize = (value: string) => value.replace(/\s/g, ' ');

describe('formatRub', () => {
  it('форматирует целые рубли без копеек', () => {
    expect(normalize(formatRub(12_599_000))).toBe('125 990 ₽');
  });

  it('показывает копейки, если они есть', () => {
    expect(normalize(formatRub(150))).toBe('1,50 ₽');
  });

  it('отклоняет дробные копейки', () => {
    expect(() => formatRub(10.5)).toThrow(RangeError);
  });
});

describe('прочие форматы', () => {
  it('рубли и разница', () => {
    expect(normalize(formatRubles(170000))).toBe('170 000 ₽');
    expect(normalize(formatRubDelta(-1_650_000))).toBe('−16 500 ₽');
    expect(normalize(formatRubDelta(900_000))).toBe('+9 000 ₽');
    expect(normalize(formatRubDelta(0))).toBe('0 ₽');
  });

  it('числа с разрядами', () => {
    expect(normalize(formatNumber(122))).toBe('122');
    expect(normalize(formatNumber(1500))).toBe('1 500');
    expect(normalize(formatNumber(2.5))).toBe('2,5');
  });

  it('FPS, минуты, проценты, доли', () => {
    expect(formatFps(105.3)).toBe('≈ 105');
    expect(formatMinutes(6.43)).toBe('6,4 мин');
    expect(formatMinutes(Infinity)).toBe('—');
    expect(formatPercent(3.25)).toBe('+3,3%');
    expect(formatPercent(-31.8)).toBe('−31,8%');
    expect(formatShare(0.959)).toBe('96%');
  });
});
