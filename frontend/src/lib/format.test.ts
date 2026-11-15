import { formatDate, formatMoney } from './format';

describe('format', () => {
  it('formats dates in the organization locale', () => {
    expect(formatDate('2027-06-12T12:00:00Z')).toBe('12.06.2027');
  });

  it('formats money from cents', () => {
    expect(formatMoney(125_000)).toMatch(/^1\.250,00\s€$/);
  });
});
