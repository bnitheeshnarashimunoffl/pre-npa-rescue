import { handlers } from './handlers';

export async function initMocks() {
  if (typeof window === 'undefined') {
    const { setupServer } = await import('msw/node');
    const server = setupServer(...handlers);
    server.listen({ onUnhandledRequest: 'bypass' });
  } else {
    const { setupWorker } = await import('msw/browser');
    const worker = setupWorker(...handlers);
    await worker.start({ onUnhandledRequest: 'bypass' });
  }
}

export { handlers };
