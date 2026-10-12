# Five-minute demo script

This is the operator script for the integrated Pre-NPA Rescue demo. It is written so a second
presenter can run it without product knowledge. Do not replace `TBD – from <path>` until the
named artifact is committed and checked.

## Demo contract

- **Length:** 5:00 hard stop.
- **Story:** day-90 problem → Priya → Ravi → proof → impact → BIS close.
- **Rule:** never improvise an offer, performance result or compliance claim.
- **Recovery:** if a live step takes more than 5 seconds, use its fallback and keep speaking.
- **Evidence mode:** say “fixture-backed” whenever the integrated provider is not available.

## Preconditions

Complete this checklist on the presentation machine before every rehearsal and the final run.

| Check | Required state | Evidence or action |
|---|---|---|
| Git build | `demo-freeze` tag; exact commit `TBD – from git rev-parse demo-freeze` | Team lead creates the tag. Do not demo an unrecorded working tree. |
| Random seed | `SEED=42` | `.env.example`; `packages/contracts/src/npa_contracts/constants.py` |
| Dataset | Final account count `TBD – from contracts/fixtures/simulation_metrics.json` after producer replacement | The current fixture is illustrative and must not be described as a real run. |
| As-of month | `2026-09` | `.env.example`; contract fixtures |
| Reset | `make demo-reset` succeeds | Requested from WS5 in [issue #83](https://github.com/bnitheeshnarashimunoffl/pre-npa-rescue/issues/83). Until merged, restart and reseed using the WS5-approved command. |
| Services | API health is green; web loads; database is ready | `make demo`; `GET /api/v1/health` |
| Presenter login | `collector1` / `demo` | Shared briefing contract; verify against the seeded demo users before freeze. |
| Customer logins | `priya` / `demo`; `ravi` / `demo` | Shared briefing contract; verify against the seeded demo users before freeze. |
| Compliance login | `auditor1` / `demo` | Shared briefing contract; verify against the seeded demo users before freeze. |
| Browser | Chromium-based browser, zoom 100%, notifications off, password prompts off | Visual rehearsal check. |
| Tamil rendering | Priya fixture text displays as joined Tamil glyphs with no tofu boxes | Compare UI with `contracts/fixtures/bot_reply_offer.json`; request native-speaker review. |
| LLM mode | Preferred: `LLM_PROVIDER=mock` with deterministic recorded replies | `.env.example`; avoids network and latency risk. |
| Live LLM option | If used, `ANTHROPIC_API_KEY` is set locally and never shown | Fall back to mock at the first timeout or malformed response. |
| Result evidence | Model, scorecard and simulation files are opened once before presenting | Paths listed in “Evidence freeze” below. |
| Backup video | Local file: `TBD – from presentation-device/pre-npa-rescue-demo.mp4`; second copy: `TBD – from team lead` | Record after `demo-freeze`; verify sound, resolution and offline playback. Do not commit a file over 5 MB. |
| Deck fallback | `docs/deck/deck.md`, RBI slide and BIS slide open offline | Exported presentation path `TBD – from team lead`. |

## Tab order

Arrange tabs left to right and never search during the demo:

1. Title/problem slide.
2. Collector dashboard, already logged in.
3. Priya Tamil chat, reset to the opening turn.
4. Ravi English chat, reset to the opening turn.
5. Compliance scorecard, latest real run selected.
6. Simulation panel.
7. BIS close slide.
8. API fixture/evidence page for emergency fallback only.

Target frontend paths must be confirmed against the merged WS6 app before `demo-freeze`.
Expected route families are `/en/...`, `/ta/...` and `/hi/...`; do not type a route live.

## Run of show

| Time | Screen | What happens | Core point |
|---|---|---|---|
| 0:00–0:30 | Title / problem | Introduce the day-90 cliff | One script harms customers and banks |
| 0:30–1:15 | Collector dashboard | Open Priya; show reasons and no-contact actions | Detect risk and decide who not to call |
| 1:15–2:15 | Priya Tamil chat | Disclose job loss; present and accept approved plan | AI proposes; policy and human approval decide |
| 2:15–3:00 | Ravi English chat | Declare zero capacity; book 11:00 callback | Stop pressure and route distress safely |
| 3:00–3:45 | Compliance scorecard | Show attacks and evidence coverage | Prove fairness and rule enforcement |
| 3:45–4:30 | Simulation panel | Compare three outcome measures | Business value, with evidence status stated |
| 4:30–5:00 | BIS slide / close | Connect standards to implementation and close | Govern, test, protect, serve and include |

## 0:00–0:30 — The problem

### Operator actions

1. Show the title slide with the 0-to-90-day line.
2. Point once to the NPA boundary; do not click away early.
3. At 0:25, move to the collector dashboard tab.

### Say exactly

“A customer who forgot, a customer who lost a job, and a customer who refuses to pay often
receive the same collections script. That is late, expensive and undignified. Pre-NPA Rescue
acts before the credit-card day-90 NPA boundary: detect emerging stress, decide where help can
change the outcome, resolve within bank rules, and prove the system is fair.”

### Fallback

If the deck fails, show the opening section of `README.md` and trace the four layers in the
architecture text diagram. Keep the same narration.

## 0:30–1:15 — Detect and decide

### Operator actions

1. Show the prioritised collector queue.
2. Click **Priya Raman**.
3. Point to **High risk**, then the reason codes for stopped salary, minimum-due streak and
   rising utilisation.
4. Point to the `cant_pay` segment and `persuadable` uplift group.
5. Return to the queue and point to at least one **No contact** action without opening it.
6. Switch to the Priya chat tab by 1:12.

### Say exactly

“Priya is visible before default. The system explains why: salary credits stopped, she has
paid only the minimum, and utilisation is rising. Risk tells us who may struggle. Uplift asks a
different question: will contact improve the outcome? Priya is persuadable, while a sleeping
dog receives no contact. We focus help where it can work and avoid unnecessary pressure.”

### Evidence and fallback

- Real model values: `TBD – from packages/models/reports/metrics.json`.
- If the dashboard is unavailable, open `contracts/fixtures/queue.json`, search
  `ACC-DEMO-PRIYA`, and show the reason codes plus the `ACC-000778` no-contact example.
- Say: “This is the versioned contract fixture; the integrated dashboard consumes the same
  shape.”

## 1:15–2:15 — Priya resolves in Tamil

### Operator actions

1. Confirm the language selector shows **தமிழ்**.
2. Use the prepared customer quick reply for job loss; do not type free text during the final
   demo.
3. Select the prepared affordability response.
4. When the plan appears, point to monthly amount, tenure, fee waiver, policy reference,
   approval identity and disclosures.
5. Click **Accept** only after those fields are visible.
6. Show the accepted confirmation, then switch to Ravi at 2:12.

### Say exactly

“Priya can explain job loss in Tamil without facing a collections script. The language model
understands the conversation, but it cannot invent money or promises. The rules engine returns
the permitted terms, and a human approval is recorded. Here the merged fixture supports
₹2,000 a month for 6 months with ₹1,180 in late fees waived. Priya sees the disclosures before
she accepts. The AI proposes; the rules decide.”

### Evidence and fallback

- Offer: `contracts/fixtures/bot_reply_offer.json` and `contracts/fixtures/offer.json`.
- If the chat stalls, switch immediately to the rendered fixture or the matching frame in the
  backup video.
- If Tamil glyphs break, use the pre-captured Tamil screenshot and say: “The text is preserved
  here while we switch away from this machine’s font-rendering issue.”
- If the integrated provider returns different valid terms, state those displayed terms and
  do not repeat the fixture amount.

## 2:15–3:00 — Ravi has zero capacity

### Operator actions

1. Confirm Ravi’s chat is in English.
2. Use the prepared response: **I cannot pay anything right now**.
3. Point out that no payment amount is requested after this disclosure.
4. Point to the job-loss insurance referral.
5. Select the 11:00 hardship-officer slot and confirm the booking.
6. Point to the recording and grievance notices; switch to scorecard at 2:57.

### Say exactly

“Ravi cannot afford even a token payment. The bot stops asking. It checks the policy-defined
insurance route and offers a human hardship callback. Ravi chooses 11:00, inside the permitted
08:00 to 19:00 contact window. This is documented engagement before escalation, designed to
the RBI financial-distress framework effective 1 January 2027—not a claim that the future
paragraph is already in force.”

### Evidence and fallback

- Handoff: `contracts/fixtures/bot_reply_zero_capacity.json` and
  `contracts/fixtures/callback.json`.
- If slot booking fails, show the callback fixture and state: “The fixture records 11:00 IST;
  the live scheduler is unavailable, so I will not claim a live booking.”
- If the only available slot differs, choose a displayed in-window slot and narrate the actual
  time instead.

## 3:00–3:45 — Prove it under attack

### Operator actions

1. Show the latest real scorecard run identifier.
2. Open one bias-swap pair and compare the decision or offer fields.
3. Open one prompt-injection case and point to the blocked request.
4. Open one contact-window case and point to the rule identifier.
5. Show RBI and BIS coverage grids; do not hide failures.
6. Move to the simulation tab at 3:42.

### Say exactly

“We do not ask judges to trust a chatbot. We attack it. Bias swaps change gender, religion or
region while holding the financial case constant. Prompt injection tries to invent a waiver.
Contact tests request an out-of-hours call. The scorecard records the output, pass or failure,
and the RBI and BIS evidence reference. Real pass rate: TBD – from the latest committed
red-team scorecard.”

### Evidence and fallback

- Final result: `TBD – from redteam/reports/<latest>/scorecard.json`.
- Schema and layout fallback: `contracts/fixtures/scorecard.json`.
- If the real run is missing, say: “This is the fixture layout, not a measured pass rate,” and
  demonstrate one stored case only.
- If a test fails live, show it. Say: “The harness has found a release blocker; this is why the
  proof layer exists.”

## 3:45–4:30 — Business impact

### Operator actions

1. Show paired baseline and Pre-NPA Rescue bars.
2. Point in order to NPA rate, cure rate and collection cost.
3. Show population, horizon and illustrative/real status.
4. Do not calculate a percentage aloud from the screen.
5. Move to the BIS slide at 4:27.

### Say exactly

“We compare targeted intervention with a call-everyone baseline on three outcomes: NPA rate,
cure rate and collection cost. Final results are TBD – from
packages/models/reports/policy_simulation.json. Until that committed run exists, this panel is
illustrative. The business hypothesis is fewer harmful or wasted contacts, more cures, and
lower cost—not a result we will claim without evidence.”

### Evidence and fallback

- Final simulation: `TBD – from packages/models/reports/policy_simulation.json` or the producer’s
  committed replacement.
- Layout fallback: `contracts/fixtures/simulation_metrics.json`, which is explicitly marked
  illustrative.
- If final results are absent, keep the watermark visible and do not read fixture values aloud.

## 4:30–5:00 — BIS alignment and close

### Operator actions

1. Show the five BIS control areas.
2. Sweep left to right: governance, fairness/quality, security, customer service,
   accessibility.
3. Point to the non-certification footnote.
4. End on the project name at 4:55; stop speaking by 5:00.

### Say exactly

“Relevant Indian Standards shape the evidence: govern the AI, test fairness and quality,
protect data, treat customers well, and include everyone. Each area maps to an artifact or
test, with final mapping TBD – from governance/bis_mapping.md. This is design alignment, not
certification. We find customers who are about to struggle, work out who we can actually help,
offer a kind and affordable plan within bank rules, and prove the whole thing is fair.”

### Fallback

If the slide is unavailable, open `docs/deck/bis_slide.md`, show the five-row grid and keep the
same narration. Do not quote an aggregate standards count until WS7 verifies the grouping.

## Evidence freeze

The operator must record the exact commit hash for each available artifact after the
`demo-freeze` tag. Missing evidence means the corresponding claim is removed or described as a
fixture/planned capability.

| Claim area | Required final artifact | Freeze commit/status |
|---|---|---|
| Model quality and fairness | `packages/models/reports/metrics.json` plus model cards | TBD |
| Policy simulation | `packages/models/reports/policy_simulation.json` or committed replacement | TBD |
| Red-team results | `redteam/reports/<latest>/scorecard.json` | TBD |
| RBI mapping | `governance/rbi_mapping.md` | TBD |
| BIS mapping | `governance/bis_mapping.md` | TBD |
| Dataset and licence | `data/ATTRIBUTION.md` | TBD |
| UI screenshots | `apps/web/screenshots/` | TBD |
| Integrated build | `demo-freeze` tag | TBD |
| Backup recording | Presentation-device and team-lead copies | TBD |

## Rehearsal log

Do not mark a rehearsal complete unless it runs from a clean reset and the final elapsed time
is recorded. File problems on the owning workstream and link the issue.

| Run | Build / mode | Elapsed | Result | Problems found | Owner issue | Follow-up |
|---|---|---:|---|---|---|---|
| 1 | TBD / mock LLM | TBD | Pending | Not rehearsed yet | — | Complete after the integrated Priya and Ravi flows land |
| 2 | TBD / mock LLM | TBD | Pending | Not rehearsed yet | — | Re-run after fixes from run 1 |
| 3 | `demo-freeze` / mock LLM | TBD | Pending | Not rehearsed yet | — | Final timed rehearsal and backup recording |

## Rehearsal acceptance criteria

- Three consecutive clean-reset runs finish at or below 5:00.
- Every tab is preloaded; no live route typing or repository searching.
- Priya’s Tamil text is visually checked and reviewed by a fluent speaker.
- Ravi’s flow stops payment prompts after zero capacity.
- Real result paths and commit hashes match the evidence freeze table.
- Any failure is visible and described honestly; no presenter improvises a pass.
- The backup video plays offline from both recorded locations.
- A second operator can complete the script using this document alone.
