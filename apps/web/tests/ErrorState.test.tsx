import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import messages from '../messages/en.json';
import { ErrorState } from '@/components/shared/ErrorState';
import { EmptyState } from '@/components/shared/EmptyState';

function renderWithIntl(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>
  );
}

describe('ErrorState & EmptyState', () => {
  it('renders API error envelope and triggers retry callback', () => {
    const handleRetry = vi.fn();
    renderWithIntl(
      <ErrorState
        error={{
          error: {
            code: 'ACCOUNT_NOT_FOUND',
            message: 'Unable to locate specified card account'
          }
        }}
        onRetry={handleRetry}
      />
    );

    expect(screen.getByText('ACCOUNT_NOT_FOUND')).toBeInTheDocument();
    expect(screen.getByText('Unable to locate specified card account')).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /Try again/i });
    fireEvent.click(retryBtn);
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('renders EmptyState with custom title and description', () => {
    renderWithIntl(
      <EmptyState
        title="No Accounts in Queue"
        description="All accounts currently within policy compliance limits."
      />
    );

    expect(screen.getByText('No Accounts in Queue')).toBeInTheDocument();
    expect(screen.getByText('All accounts currently within policy compliance limits.')).toBeInTheDocument();
  });
});
