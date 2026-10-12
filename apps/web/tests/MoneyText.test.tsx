import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MoneyText, formatINR } from '@/components/shared/MoneyText';

describe('MoneyText component & formatINR', () => {
  it('formats paise correctly into INR', () => {
    // 200,000 paise = 2,000 rupees
    expect(formatINR(200000)).toMatch(/₹\s?2,000/);
    // 1,318,000 paise = 13,180 rupees
    expect(formatINR(1318000)).toMatch(/₹\s?13,180/);
  });

  it('renders formatted INR inside span element', () => {
    render(<MoneyText paise={200000} />);
    const el = screen.getByText(/2,000/);
    expect(el).toBeInTheDocument();
  });

  it('renders dash for null or undefined', () => {
    const { rerender } = render(<MoneyText paise={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();

    rerender(<MoneyText paise={undefined} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('handles zero paise properly', () => {
    render(<MoneyText paise={0} showZero={true} />);
    expect(screen.getByText(/0/)).toBeInTheDocument();
  });
});
