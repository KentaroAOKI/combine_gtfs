# combine gtfs

This repository merges multiple GTFS archives into a single GTFS archive.

## Prerequisites
- Python 3.8+ (ships with the `scripts/combine_gtfs.py` utility)
- Java (for running the Google GTFS Validator CLI)

## Combine All Feeds
```bash
python3 scripts/combine_gtfs.py --output-dir out_data --basename feed_multi_combined
```
- If no inputs are supplied, every `*.zip` in `gtfs_data/` is merged.
- The script prefixes IDs with each source filename, fills missing `agency_id` fields, deduplicates rows, drops orphan translations, and synthesizes shapes for trips lacking `shape_id` by tracing their ordered `stop_times`.
- The resulting archive is written to `out_data/feed_multi_combined_<startdate>_<timestamp>.zip`.

To limit the merge to specific feeds, pass their paths explicitly:
```bash
python3 scripts/combine_gtfs.py --output-dir gtfs_data gtfs_data/*.zip feeds/a.zip feeds/b.zip
```

## Validate The Combined Feed
After generating a new archive, run the GTFS Validator and review the output directory for ERROR notices.
```bash
java -jar gtfs-validator-7.1.0-cli.jar \
  -i gtfs_data/feed_multi_combined_<startdate>_<timestamp>.zip \
  -o tmp/validator-report
```

Please download gtfs-validator-7.1.0-cli.jar in advance.
```bash
wget https://github.com/MobilityData/gtfs-validator/releases/download/v7.1.0/gtfs-validator-7.1.0-cli.jar
```

Expect WARN/INFO categories for localized content (e.g., mixed scripts). Treat any ERROR-level findings as blockers; adjust the merge script or upstream feeds before publishing.

## Minimize A Single Feed
To shrink a standalone GTFS archive by shortening identifier columns and rounding coordinates to six decimal places:
```bash
python3 scripts/minimize_gtfs_ids.py gtfs_data/feed_example.zip tmp/feed_example_min.zip
```
- Identifier domains (e.g., `stop_id`, `trip_id`, `shape_id`) are remapped to compact tokens while preserving referential integrity across tables.
- `shape_pt_lat`, `shape_pt_lon`, `stop_lat`, and `stop_lon` values are rounded to six decimal places.
- Always validate the minimized output before distribution. The GTFS Validator will highlight any regressions.

## Housekeeping
- Keep `gtfs_data/` filenames in alphabetical order to minimize diff noise.
- Do not commit extracted feed contents; regenerate archives via the script when fixes are required.
- Record provenance (source URL, release notes, validator summary) in commit bodies or PR descriptions for traceability.
