Title: Add Step 4 breakout and false-break detection to the unified application

This PR extends the unified four-method application with the Close-based rules
from the Breakdown Point Report. Existing swing algorithms, shared trendline
construction and all eight indicators are preserved.

Changes:
- Detect the first breakout above falling resistance or breakdown below rising support.
- Track time confirmation and false-break outcomes separately, using configurable
  consecutive-close and follow-up counts (defaults: 2 and 5).
- Scan all eligible lines with fixed original geometry and the existing tolerance;
  never use final chart ranking to choose historical events.
- Add CLI parameters, GUI controls, an event table and a dedicated breakout chart.
- Export breakouts.csv/json/png and Step 4 counts/settings in run_summary.json.
- Include original-data and four-method TSLA examples, tests and usage documentation.

Validation:
- Automated tests cover both directions, exact thresholds, wick-only crossings,
  confirmation followed by failure, incomplete follow-up, inclusive deadlines,
  timestamp gaps, four-method prefix replay, exports and GUI snapshot handling.
- Existing legacy swing/trendline reference checks remain unchanged.
- For five example runs, the eight original non-summary outputs are byte-identical
  to unified; all previous run_summary.json fields retain their values.
- See STEP4_TEST_RESULTS.txt for the complete test log.

Scope:
- Step 4 currently supports Close-based trendlines only. High/Low mode retains its
  existing functionality and explicitly reports Step 4 as unsupported.
- ATR breakout buffers, volume/retest filters and wick-rejection records are deferred.
- GUI callbacks are tested with mock widgets; native macOS visual testing is still needed.
