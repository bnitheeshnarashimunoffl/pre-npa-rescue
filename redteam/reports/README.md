# redteam/reports/

Each red-team run can write `RT-YYYYMMDD-HHMM/` here (`npa-redteam run --out redteam/reports`):

| File | What |
|---|---|
| `scorecard.json` | Contract `Scorecard` (A7.3), served by `GET /redteam/scorecard/latest` |
| `report.json` | Full WS7 run report: per-language counts, coverage detail with evidence, skipped cases, WS2 fairness |
| `summary.md` | The same for people: judges, reviewers, the WS8 deck |

**Commit policy.** Commit only runs against the real system, meaning the best demo run and the
re-test runs linked from `bug` + `redteam` issues. Runs against the fixture fakes
(`target=library:fixtures`) prove the harness, not the system; their summary says so, and they
are not committed. Never edit a committed report by hand: re-run instead.
