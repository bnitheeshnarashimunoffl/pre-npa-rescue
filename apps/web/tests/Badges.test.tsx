import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import messages from '../messages/en.json';
import { RiskBadge } from '@/components/shared/RiskBadge';
import { BucketBadge } from '@/components/shared/BucketBadge';
import { SegmentBadge } from '@/components/shared/SegmentBadge';
import { UpliftBadge } from '@/components/shared/UpliftBadge';

function renderWithIntl(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>
  );
}

describe('Shared Badges', () => {
  it('renders RiskBadge with band and probability', () => {
    renderWithIntl(<RiskBadge band="high" probability={0.82} />);
    expect(screen.getByText(/High Risk/)).toBeInTheDocument();
    expect(screen.getByText(/82%/)).toBeInTheDocument();
  });

  it('renders BucketBadge with DPD indicator', () => {
    renderWithIntl(<BucketBadge bucket="sma0" dpd={12} />);
    expect(screen.getByText(/SMA-0/)).toBeInTheDocument();
    expect(screen.getByText(/12 DPD/)).toBeInTheDocument();
  });

  it('renders SegmentBadge for cant_pay', () => {
    renderWithIntl(<SegmentBadge segment="cant_pay" />);
    expect(screen.getByText(/Cannot Pay/)).toBeInTheDocument();
  });

  it('renders UpliftBadge for persuadable', () => {
    renderWithIntl(<UpliftBadge upliftGroup="persuadable" />);
    expect(screen.getByText(/Persuadable/)).toBeInTheDocument();
  });
});
