# redteam/reports/

Each red-team run can write `RT-YYYYMMDD-HHMM/` here (`npa-redteam run --out redteam/reports`):

| File | What |
|---|---|
| `scorecard.json` | Contract `Scorecard` (A7.3), served by `GET /redteam/scorecard/latest` |
| `report.json` | Full WS7 run report: per-language counts, coverage detail with evidence, skipped cases, WS2 fairness |
| `summary.md` | The same for people: judges, reviewers, the WS8 deck |

**Commit policy.** Commit the best demo run and the re-test runs linked from `bug` + `redteam`
issues. Never edit a committed report by hand: re-run instead.

Runs against the fixture fakes (`target=library:fixtures`) prove the harness, not the system,
and their summary says so in bold. The one exception is a labelled **harness baseline**,
committed so WS6 and WS8 have real-shaped data before integration. It is replaced by a
real-system run once WS3's rules and WS4's bot are wired in.

| Run | Target | What it is |
|---|---|---|
| `RT-20261012-1530` | `library:fixtures` | Harness baseline: all 159 cases, seed 42, deterministic. 107 passed, 35 failed, 17 skipped. **Not a system result** |
