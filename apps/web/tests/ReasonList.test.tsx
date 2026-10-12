import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import messages from '../messages/en.json';
import { ReasonList } from '@/components/shared/ReasonList';

describe('ReasonList component', () => {
  const sampleReasons = [
    {
      code: 'SALARY_STOPPED',
      weight: 0.41,
      text: {
        en: 'Salary credits have stopped in the last 3 months.',
        ta: 'கடந்த 3 மாதங்களாக சம்பளம் வரவு வைக்கப்படவில்லை.',
        hi: 'पिछले 3 महीनों से वेतन जमा नहीं हुआ है।'
      }
    },
    {
      code: 'MIN_DUE_ONLY_STREAK',
      weight: 0.27,
      text: {
        en: 'Only the minimum due has been paid for 3 months in a row.',
        ta: 'தொடர்ந்து 3 மாதங்களாக குறைந்தபட்சத் தொகை மட்டுமே செலுத்தப்பட்டுள்ளது.',
        hi: 'लगातार 3 महीनों से केवल न्यूनतम देय राशि का भुगतान हुआ है।'
      }
    }
  ];

  it('renders localized reasons and weights', () => {
    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ReasonList reasons={sampleReasons} />
      </NextIntlClientProvider>
    );

    expect(screen.getByText('Salary credits have stopped in the last 3 months.')).toBeInTheDocument();
    expect(screen.getByText('Influence: 41%')).toBeInTheDocument();
    expect(screen.getByText('Only the minimum due has been paid for 3 months in a row.')).toBeInTheDocument();
    expect(screen.getByText('Influence: 27%')).toBeInTheDocument();
  });
});
