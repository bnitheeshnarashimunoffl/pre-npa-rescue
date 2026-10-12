import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DateTimeText, formatIST } from '@/components/shared/DateTimeText';

describe('DateTimeText component & formatIST', () => {
  it('formats UTC timestamp into Asia/Kolkata timezone', () => {
    // 2026-10-12T04:30:00Z is 10:00 IST
    const formatted = formatIST('2026-10-12T04:30:00Z', true);
    expect(formatted).toContain('12');
    expect(formatted).toContain('Oct');
    expect(formatted).toContain('2026');
    expect(formatted).toContain('10:00');
  });

  it('renders semantic time element with dateTime attribute', () => {
    const iso = '2026-10-12T04:30:00Z';
    render(<DateTimeText date={iso} />);
    const timeEl = screen.getByRole('time', { hidden: true }) || document.querySelector('time');
    expect(timeEl).not.toBeNull();
    expect(timeEl?.getAttribute('dateTime')).toBe(iso);
    expect(timeEl?.textContent).toContain('IST');
  });

  it('renders dash when date is null or invalid', () => {
    render(<DateTimeText date={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
