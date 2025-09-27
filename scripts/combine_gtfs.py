#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import io
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import zipfile

PREFIX_COLUMNS = {
    "agency_id",
    "attribution_id",
    "block_id",
    "fare_id",
    "from_stop_id",
    "level_id",
    "location_id",
    "location_group_id",
    "origin_id",
    "parent_station",
    "pathway_id",
    "route_id",
    "service_id",
    "shape_id",
    "stop_id",
    "to_stop_id",
    "trip_id",
    "zone_id",
    "contains_id",
    "destination_id",
    "transfer_id",
    "network_id",
    "area_id",
    "stop_area_id",
    "route_network_id",
    "feed_id",
    "vehicle_id",
    "journey_pattern_id",
    "journey_pattern_variant_id",
    "service_pattern_id",
    "schedule_id",
    "fare_media_id",
    "fare_product_id",
    "fare_leg_group_id",
    "fare_transfer_type_id",
    "rider_category_id",
}

EXCLUDED_ID_COLUMNS = {
    "direction_id",
}

DATE_FIELDS = {
    "start_date",
    "end_date",
    "date",
    "feed_start_date",
    "feed_end_date",
}

GTFS_TXT_EXT = ".txt"
FALLBACK_ENCODINGS = ("utf-8-sig", "cp932", "shift_jis", "latin-1")
DEFAULT_TIMEZONE = "Asia/Tokyo"


def detect_date(value: str):
    if value and len(value) == 8 and value.isdigit():
        try:
            return dt.datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            return None
    return None


def merge_fieldnames(existing: List[str], new_fields: Iterable[str]) -> List[str]:
    seen = set(existing)
    merged = list(existing)
    for field in new_fields:
        if field not in seen:
            merged.append(field)
            seen.add(field)
    return merged


def prefix_value(value: str, prefix: str) -> str:
    if not value:
        return value
    return f"{prefix}_{value}"


def apply_prefix(row: Dict[str, str], prefix: str) -> Dict[str, str]:
    out = {}
    for key, value in row.items():
        if not key:
            # Skip malformed columns with empty headers.
            continue
        if key in PREFIX_COLUMNS or (key.endswith("_id") and key not in EXCLUDED_ID_COLUMNS):
            out[key] = prefix_value(value, prefix)
        else:
            out[key] = value
    return out


def parse_gtfs_time(value: str) -> Optional[int]:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return None
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60 or hours < 0:
        return None
    return hours * 3600 + minutes * 60 + seconds


def format_gtfs_time(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def normalize_header(fieldnames: Iterable[str]) -> List[str]:
    header: List[str] = []
    seen: set = set()
    for name in fieldnames or []:
        normalized = (name or "").strip()
        if not normalized or "," in normalized:
            continue
        if normalized not in seen:
            header.append(normalized)
            seen.add(normalized)
    return header


def normalize_keys(row: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in row.items():
        normalized_key = (key or "").strip()
        if not normalized_key or "," in normalized_key:
            continue
        if normalized_key not in normalized or not normalized[normalized_key]:
            normalized[normalized_key] = value.strip() if isinstance(value, str) else value
    return normalized


def normalize_row(
    filename: str,
    row: Dict[str, str],
    prefix: str,
    feed_context: Dict[str, object],
) -> Optional[Dict[str, str]]:
    """Clean row-level issues the validator flags as errors."""

    if filename == "translations.txt":
        # Drop incomplete translation entries missing required identifiers.
        if not row.get("table_name") or not row.get("field_name"):
            return None
        if not row.get("language"):
            if row.get("translation"):
                row["language"] = "en"
            else:
                return None
        if not row.get("record_id"):
            return None

    if filename == "feed_info.txt":
        url = row.get("feed_contact_url", "")
        if url and "@" in url and not url.lower().startswith(("http://", "https://")):
            if not row.get("feed_contact_email"):
                row["feed_contact_email"] = url
            row["feed_contact_url"] = ""
        version = row.get("feed_version")
        if version:
            row["feed_version"] = version.replace("\r", " ").replace("\n", " ").strip()

    if filename == "agency.txt":
        if not row.get("agency_id"):
            counter = feed_context.setdefault("agency_counter", 0) + 1
            feed_context["agency_counter"] = counter
            row["agency_id"] = f"{prefix}_agency_{counter}"
        feed_context.setdefault("agency_ids", []).append(row["agency_id"])
        if not row.get("agency_timezone"):
            row["agency_timezone"] = DEFAULT_TIMEZONE
        if not row.get("agency_lang") and row.get("feed_lang"):
            row["agency_lang"] = row["feed_lang"]

    if filename in {"routes.txt", "fare_attributes.txt"}:
        if not row.get("agency_id"):
            agencies = feed_context.get("agency_ids", [])
            if agencies:
                row["agency_id"] = agencies[0]

    if filename == "shapes.txt":
        if not row.get("shape_id") or not row.get("shape_pt_lat") or not row.get("shape_pt_lon"):
            return None
        if not row.get("shape_pt_sequence"):
            return None

    if filename == "stop_times.txt":
        arr = (row.get("arrival_time") or "").strip()
        dep = (row.get("departure_time") or "").strip()
        if arr and not dep:
            row["departure_time"] = arr
            dep = arr
        elif dep and not arr:
            row["arrival_time"] = dep
            arr = dep
        if not arr and not dep and row.get("timepoint") == "1":
            row["timepoint"] = "0"
        if not row.get("stop_sequence"):
            return None

    return row


def decode_bytes(raw: bytes) -> str:
    for encoding in FALLBACK_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", raw, 0, 0, "Unable to decode GTFS text file")


def collect_feeds(feed_paths: List[Path]):
    combined: Dict[str, List[Dict[str, str]]] = {}
    fieldnames: Dict[str, List[str]] = {}
    dedupe_keys: Dict[str, set] = {}
    earliest_date = None
    feed_contexts: Dict[str, Dict[str, object]] = {}

    for feed_path in feed_paths:
        prefix = feed_path.stem
        feed_context = feed_contexts.setdefault(prefix, {})
        with zipfile.ZipFile(feed_path, "r") as zf:
            for member in sorted(zf.infolist(), key=lambda m: m.filename):
                if member.is_dir():
                    continue
                name = member.filename
                if not name.lower().endswith(GTFS_TXT_EXT):
                    continue
                with zf.open(member, "r") as fh:
                    raw = fh.read()
                text = decode_bytes(raw)
                reader = csv.DictReader(io.StringIO(text))
                header = normalize_header(reader.fieldnames or [])
                rows = []
                for row in reader:
                    normalized_keys = normalize_keys(row)
                    prefixed = apply_prefix(normalized_keys, prefix)
                    normalized = normalize_row(name, prefixed, prefix, feed_context)
                    if normalized is None:
                        continue
                    key = tuple(sorted(normalized.items()))
                    seen = dedupe_keys.setdefault(name, set())
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(normalized)
                    for date_field in DATE_FIELDS.intersection(row.keys()):
                        candidate = detect_date(row.get(date_field, ""))
                        if candidate is not None:
                            if earliest_date is None or candidate < earliest_date:
                                earliest_date = candidate
                if not rows:
                    continue
                if name not in combined:
                    combined[name] = rows
                    fieldnames[name] = header
                else:
                    fieldnames[name] = merge_fieldnames(fieldnames[name], header)
                    combined[name].extend(rows)
    if not combined:
        raise RuntimeError("No GTFS text files found in the provided feeds")
    return combined, fieldnames, earliest_date


def write_combined_zip(output_path: Path, combined: Dict[str, List[Dict[str, str]]], fieldnames: Dict[str, List[str]]):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference_tables = {
        "agency": ("agency.txt", "agency_id"),
        "fare_attributes": ("fare_attributes.txt", "fare_id"),
        "routes": ("routes.txt", "route_id"),
        "shapes": ("shapes.txt", "shape_id"),
        "stops": ("stops.txt", "stop_id"),
        "trips": ("trips.txt", "trip_id"),
    }
    reference_sets: Dict[str, set] = {}
    for table, (filename, key_field) in reference_tables.items():
        if filename in combined:
            keys = {row.get(key_field, "") for row in combined[filename] if row.get(key_field)}
            reference_sets[table] = keys
    zone_ids = set()
    for row in combined.get("stops.txt", []):
        zone = row.get("zone_id")
        if zone:
            zone_ids.add(zone)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
        for name in sorted(combined.keys()):
            rows = combined[name]
            if name == "translations.txt":
                filtered = []
                for row in rows:
                    table_name = row.get("table_name")
                    record_id = row.get("record_id")
                    if table_name not in reference_sets:
                        continue
                    if record_id and record_id not in reference_sets[table_name]:
                        continue
                    filtered.append(row)
                rows = filtered
            elif name == "fare_rules.txt" and zone_ids:
                filtered = []
                for row in rows:
                    invalid = False
                    for key in ("origin_id", "destination_id", "contains_id"):
                        value = row.get(key)
                        if value and value not in zone_ids:
                            invalid = True
                            break
                    if not invalid:
                        filtered.append(row)
                rows = filtered
            elif name == "trips.txt" and "shapes" in reference_sets:
                for row in rows:
                    if row.get("shape_id") and row["shape_id"] not in reference_sets["shapes"]:
                        row["shape_id"] = ""
            elif name == "stop_times.txt":
                if "stops" in reference_sets:
                    rows = [row for row in rows if row.get("stop_id") in reference_sets["stops"]]
                if "trips" in reference_sets:
                    rows = [row for row in rows if row.get("trip_id") in reference_sets["trips"]]
                def sort_key(record: Dict[str, str]):
                    trip = record.get("trip_id", "")
                    seq_str = record.get("stop_sequence", "")
                    try:
                        seq = int(seq_str)
                    except ValueError:
                        seq = 0
                    return (trip, seq)

                rows.sort(key=sort_key)

                current_trip = None
                last_time = None
                last_shape = None
                for row in rows:
                    trip_id = row.get("trip_id")
                    if trip_id != current_trip:
                        current_trip = trip_id
                        last_time = None
                        last_shape = None

                    arr_seconds = parse_gtfs_time(row.get("arrival_time", ""))
                    dep_seconds = parse_gtfs_time(row.get("departure_time", ""))

                    if arr_seconds is not None and dep_seconds is None:
                        dep_seconds = arr_seconds
                        row["departure_time"] = format_gtfs_time(dep_seconds)
                    elif dep_seconds is not None and arr_seconds is None:
                        arr_seconds = dep_seconds
                        row["arrival_time"] = format_gtfs_time(arr_seconds)

                    if last_time is not None:
                        if arr_seconds is not None and arr_seconds < last_time:
                            arr_seconds = last_time
                            row["arrival_time"] = format_gtfs_time(arr_seconds)
                        if dep_seconds is not None:
                            min_allowed = arr_seconds if arr_seconds is not None else last_time
                            if dep_seconds < min_allowed:
                                dep_seconds = min_allowed
                                row["departure_time"] = format_gtfs_time(dep_seconds)

                    if dep_seconds is not None:
                        last_time = dep_seconds
                    elif arr_seconds is not None:
                        last_time = arr_seconds

                    shape_dist = row.get("shape_dist_traveled")
                    if shape_dist:
                        try:
                            dist_value = float(shape_dist)
                        except ValueError:
                            row["shape_dist_traveled"] = ""
                        else:
                            if last_shape is not None and dist_value <= last_shape:
                                row["shape_dist_traveled"] = ""
                            else:
                                last_shape = dist_value
            header = fieldnames[name]
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                record = {key: row.get(key, "") for key in header}
                writer.writerow(record)
            out_zip.writestr(name, buffer.getvalue().encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Combine multiple GTFS feeds into one archive with prefixed IDs")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Specific GTFS feed ZIPs to merge. If omitted, all ZIPs in gtfs_data/ are used.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("gtfs_data"),
        help="Directory where the combined GTFS ZIP will be written.",
    )
    parser.add_argument(
        "--basename",
        default="feed_multi_combined",
        help="Base filename (without date/timestamp) for the combined feed.",
    )
    args = parser.parse_args()

    if args.inputs:
        feed_paths = [path for path in args.inputs]
    else:
        gtfs_dir = Path("gtfs_data")
        feed_paths = sorted(gtfs_dir.glob("*.zip"))
    if not feed_paths:
        print("No input GTFS feeds found", file=sys.stderr)
        sys.exit(1)

    combined, fieldnames, earliest_date = collect_feeds(feed_paths)

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    if earliest_date is None:
        start_date_token = dt.date.today().strftime("%Y%m%d")
    else:
        start_date_token = earliest_date.strftime("%Y%m%d")

    output_filename = f"{args.basename}_{start_date_token}_{timestamp}.zip"
    output_path = args.output_dir / output_filename
    write_combined_zip(output_path, combined, fieldnames)

    print(
        f"Combined {len(feed_paths)} feeds into {output_path} "
        f"(start_date={start_date_token}, timestamp={timestamp})"
    )


if __name__ == "__main__":
    main()
