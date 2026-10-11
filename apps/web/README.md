# web (Next.js)

**Owner:** WS6 (Frontend)

Next.js 15 App Router + React 19 + TypeScript strict, Tailwind 4 + shadcn/ui, next-intl
(en/ta/hi), TanStack Query, MSW mocks from `contracts/fixtures/`. Package manager: pnpm 9.

**Tasks:** 6.1 design system & shell · 6.2 customer chat · 6.3 collector dashboard · 6.4 scorecard · 6.5 policy admin · 6.6 multilingual & accessibility · 6.7 wellness view (stretch)

> Bootstrap stub created by WS5. The owner replaces this README with: purpose, public API,
> how to run, and which RBI/BIS items the package implements (A9).

CI's web job starts running once `apps/web/pnpm-lock.yaml` is committed. It runs
`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, and (once
`lib/api/types.ts` exists) checks it matches
`pnpm exec openapi-typescript ../../contracts/openapi.yaml -o lib/api/types.ts`.
