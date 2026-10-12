# Pre-NPA Rescue — Web Application (`apps/web`)

**Workstream:** WS6 (Frontend)  
**Stack:** Next.js 15 (App Router), React 19, TypeScript 5 (strict), Tailwind CSS 4, next-intl (en, ta, hi), TanStack Query 5, openapi-fetch, MSW 2 (Mock Service Worker).

---

## 1. Overview & Purpose
`apps/web` is the user-facing interface of **Pre-NPA Rescue**, a proactive, compassionate credit-card financial distress resolution platform designed under Reserve Bank of India (RBI) directions and Bureau of Indian Standards (BIS) quality, fairness, and accessibility benchmarks.

The application serves five core user personas:
1. **Cardholder Hardship Chat** (`/[locale]/chat`): Multilingual, judgement-free conversational experience with early-stress detection, fee waivers, transparent EMI restructuring, and an automated zero-capacity care path.
2. **Collector Intelligence Dashboard** (`/[locale]/dashboard`): Uplift-targeted collection queue, explainable risk driver codes (SHAP-backed), and real-time contact-window compliance enforcement.
3. **Hardship Officer Console** (`/[locale]/dashboard?view=hardship`): Human-in-the-loop review of distressed borrower callbacks, insurance claim referrals, and senior relief approvals.
4. **Compliance Scorecard** (`/[locale]/scorecard`): Automated red-team test auditor console reporting attack harness results, bias swap equivalence, and coverage across RBI regulations and BIS standards.
5. **Bank Policy Engine Admin** (`/[locale]/policy`): Board-approved relief options, waiver caps, and contact rules configuration (the AI strictly offers what the policy defines).
6. **Credit Wellness** (`/[locale]/wellness`): Illustrative trajectory comparing timely plan adherence against NPA credit impact.

---

## 2. Regulatory & Standards Alignment

| Standard / Direction | Scope & Implementation | Location |
|---|---|---|
| **RBI RBC Directions 2026 (Para 454Y)** | Strict 08:00 – 19:00 IST contact window enforcement, display, and audit warnings. | Header, Footer, Dashboard compliance guard |
| **RBI RBC Directions 2026 (Para 454Z)** | Banned harsh practices: calm, respectful design system; no aggressive or alarmist red debt styling aimed at borrowers. | `app/globals.css`, `components/shared/` |
| **RBI Credit Card Directions 2025** | Late charges and interest transparency; mandatory pre-reporting disclosures. | `components/shared/MoneyText.tsx`, Chat Offer Cards |
| **IS 17802 (Part 1 & 2):2021/2022** | ICT Accessibility: Screen-reader support, skip links, semantic landmarks, high contrast (≥ 4.5:1), visible focus rings, reduced motion. | `ACCESSIBILITY.md`, `components/layout/AppShell.tsx` |
| **IS/ISO 10002:2018** | Complaints handling: formal complaint capture, docket generation, grievance officer details, and direct link to RBI CMS Portal (`https://cms.rbi.org.in`). | `Footer.tsx`, Chat Complaint Cards |
| **IS 18295-1 / 18295-2:2017** | Customer contact centre service metrics and KPI display. | Collector KPI Bar |
| **IS/ISO/IEC 42001 & 23894** | AI governance and risk management: explainability reason codes, human approval gates for relief proposals. | `ReasonList.tsx`, Offer approval badges |

---

## 3. Getting Started & Development

### Prerequisites
- Node.js ≥ 20 LTS
- pnpm 9

### Installation
```bash
cd apps/web
pnpm install
```

### Development Server
```bash
pnpm dev
```
Starts the Next.js server on `http://localhost:3000`. By default, `NEXT_PUBLIC_USE_MOCKS=true` runs the app fully offline against the contract fixtures in `contracts/fixtures/`.

### Commands
- `pnpm build`: Next.js production build with static generation and typechecking.
- `pnpm lint`: ESLint code quality check.
- `pnpm typecheck`: TypeScript strict type validation.
- `pnpm test`: Run Vitest unit tests for components, money formatting, and badges.
- `pnpm gen:api`: Regenerates `lib/api/types.ts` from root `contracts/openapi.yaml`.
- `pnpm i18n:check`: Validates that all translation keys exist across `en`, `ta`, and `hi`.

---

## 4. Architecture & Key Modules

- `app/[locale]/`: Localized App Router pages (`/en`, `/ta`, `/hi`).
- `components/layout/`: `AppShell`, `Header`, `Footer`, `LanguageSwitcher`, and `StaffSidebar`.
- `components/shared/`: Shared domain components:
  - `MoneyText`: Indian Rupee formatting (`Intl.NumberFormat('en-IN')` on `paise / 100`).
  - `DateTimeText`: `Asia/Kolkata` timezone date/time formatting.
  - `RiskBadge`, `BucketBadge`, `SegmentBadge`, `UpliftBadge`: Categorization indicators with non-alarmist, accessible color tokens.
  - `ReasonList`: Explainability reason codes with localized text and relative influence bars.
  - `EmptyState`, `ErrorState`: Accessible empty and API error envelope renderers.
- `lib/api/`: Typed API client (`client.ts`) and auto-generated OpenAPI TypeScript definitions (`types.ts`).
- `mocks/`: MSW 2 handlers returning mock data directly from `contracts/fixtures/*.json`.
- `messages/`: Localization message catalogs (`en.json`, `ta.json`, `hi.json`).
