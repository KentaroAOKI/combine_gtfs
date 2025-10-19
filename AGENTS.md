# Repository Guidelines

## Project Structure & Module Organization
- `gtfs_data/` stores all GTFS feed archives; retain the alphabetical ordering so diffs stay minimal.
- Name archives `feed_<jurisdiction>_<service>_<startdate>_<timestamp>.zip` using lowercase, underscores, and `YYYYMMDD` dates taken from the official timetable release.
- Do not check in extracted contents; review ZIP metadata locally before committing to keep the repository lean.

## Build, Test, and Development Commands
- `ls gtfs_data | sort` shows every archived feed and helps verify naming consistency before opening a PR.
- `unzip -l gtfs_data/feed_example.zip` inspects the package contents; confirm required GTFS files (e.g., `stops.txt`, `trips.txt`) are present.
- `java -jar gtfs-validator-7.1.0-cli.jar -i out_data/feed_example.zip -o tmp/validator-report` (Google GTFS Validator) checks schema compliance; scrub the HTML report of PII before sharing summaries.
- `python3 scripts/combine_gtfs.py gtfs_data/*.zip --output-dir out_data --basename feed_multi_combined` merges all archives with prefixed IDs and writes `out_data/feed_multi_combined_<startdate>_<timestamp>.zip`.
- `python3 scripts/minimize_gtfs_ids.py gtfs_data/feed_example.zip tmp/feed_example_min.zip` rewrites identifier-heavy columns and rounds lat/lon to reduce package size; validate the minimized ZIP before distribution.
- After regenerating the combined feed, rerun `java -jar gtfs-validator-7.1.0-cli.jar -i out_data/feed_multi_combined_<...>.zip -o tmp/validator-report` and confirm no ERROR notices remain.

## Coding Style & Naming Conventions
- Stick to lowercase ASCII and underscores; avoid spaces and locale-specific characters in filenames to preserve cross-platform compatibility.
- When updating an existing feed, bump only the trailing timestamp segment and keep earlier tokens untouched to preserve discoverability.
- Document the upstream data portal URL and release notes in the commit body so reviewers can trace provenance quickly.

## Testing Guidelines
- Run `unzip -t gtfs_data/feed_example.zip` to verify archive integrity after compressing or modifying feeds.
- Capture validator warnings in `notes/` or the PR description; flag blocking errors so reviewers know whether a feed is production-ready or experimental.
- For large updates, spot-check stop counts or trip totals with a quick script (e.g., `python -m zipfile --list`) and summarize findings in the PR.

## Commit & Pull Request Guidelines
- Follow an imperative Conventional-Commit style: `fix(scripts): ignore blank columns when prefixing`.
- Group unrelated feed updates into separate commits to simplify future rollbacks and blame queries.
- Pull requests should include: scope summary, source URL, validation command output snippet, and any coverage gaps reviewers should know about.
- Attach diffs or screenshots only when they clarify validator findings; otherwise rely on textual summaries to keep the discussion searchable.

## Data Refresh Workflow
- Confirm the upstream publication date and changelog before refreshing; if unchanged, note the skipped update in issue comments rather than committing.
- Stage new archives with `git add gtfs_data/<file>` and review `git status` to ensure no temporary files are included.
- After merge, tag the release or update the dataset index (if maintained externally) so downstream consumers can automate pulls.

## Combined Feed Notes
- `scripts/combine_gtfs.py` normalizes missing agency IDs, drops orphan translations, and deduplicates records during aggregation. Update the script instead of hand-editing generated ZIP contents.
- Trips lacking `shape_id` now receive generated shapes built from their `stop_times` sequences; keep `stops.txt` geometry accurate to avoid downstream routing issues.
- Validator WARN/INFO notices are expected for localized data; treat any reintroduced ERROR-level findings as blockers before shipping the combined feed.
