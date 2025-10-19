#!/usr/bin/env python3
"""Shrink GTFS identifier strings to reduce archive size.

The script remaps selected identifier columns to compact sequential tokens while
maintaining referential integrity within each identifier domain.
"""

import argparse
import csv
import io
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import zipfile

FALLBACK_ENCODINGS: Tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "cp932",
    "shift_jis",
    "latin-1",
)

TARGET_COLUMNS = (
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
)

# Columns that share the same identifier domain.
COLUMN_GROUPS: Dict[str, str] = {
    "parent_station": "stop_id",
    "from_stop_id": "stop_id",
    "to_stop_id": "stop_id",
    "location_id": "stop_id",
    "origin_id": "zone_id",
    "destination_id": "zone_id",
    "contains_id": "zone_id",
}

TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

LAT_LON_COLUMNS = {
    "shape_pt_lat",
    "shape_pt_lon",
    "stop_lat",
    "stop_lon",
}


def decode_bytes(raw: bytes) -> str:
    for encoding in FALLBACK_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", raw, 0, 0, "Unable to decode GTFS text file")


def generate_token(index: int) -> str:
    base = len(TOKEN_ALPHABET)
    if base == 0:
        raise ValueError("Token alphabet must not be empty")
    digits = []
    current = index
    while True:
        digits.append(TOKEN_ALPHABET[current % base])
        current //= base
        if current == 0:
            break
    return "".join(reversed(digits))


def load_gtfs_zip(zip_path: Path):
    entries = []
    id_values: Dict[str, OrderedDict] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in sorted(zf.infolist(), key=lambda item: item.filename):
            if member.is_dir():
                continue
            data = zf.read(member.filename)
            if not member.filename.lower().endswith(".txt"):
                entries.append((member.filename, "binary", data))
                continue
            text = decode_bytes(data)
            reader = csv.DictReader(io.StringIO(text))
            header = reader.fieldnames or []
            rows: List[Dict[str, str]] = []
            for row in reader:
                rows.append({key: value for key, value in row.items()})
                for column in header:
                    if column not in TARGET_COLUMNS:
                        continue
                    value = row.get(column, "")
                    if not value:
                        continue
                    group = COLUMN_GROUPS.get(column, column)
                    bucket = id_values.setdefault(group, OrderedDict())
                    if value not in bucket:
                        bucket[value] = None
            entries.append((member.filename, "text", (header, rows)))
    return entries, id_values


def build_mapping(id_values: Dict[str, OrderedDict]) -> Dict[str, Dict[str, str]]:
    mappings: Dict[str, Dict[str, str]] = {}
    for group, bucket in id_values.items():
        group_mapping: Dict[str, str] = {}
        for index, value in enumerate(bucket.keys()):
            group_mapping[value] = generate_token(index)
        mappings[group] = group_mapping
    return mappings


def write_minimized_zip(entries, mappings: Dict[str, Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
        for name, kind, payload in entries:
            if kind == "binary":
                out_zip.writestr(name, payload)
                continue
            header, rows = payload
            with out_zip.open(name, "w") as raw_entry:
                with io.TextIOWrapper(raw_entry, encoding="utf-8", newline="") as text_writer:
                    writer = csv.DictWriter(text_writer, fieldnames=header, lineterminator="\n")
                    writer.writeheader()
                    for row in rows:
                        out_row = dict(row)
                        for column in header:
                            current = out_row.get(column, "")
                            if not current:
                                continue
                            if column in LAT_LON_COLUMNS:
                                try:
                                    out_row[column] = f"{float(current):.6f}"
                                    current = out_row[column]
                                except ValueError:
                                    pass
                            if column not in TARGET_COLUMNS:
                                continue
                            group = COLUMN_GROUPS.get(column, column)
                            mapped = mappings.get(group, {}).get(current)
                            if mapped is None:
                                mapped = current
                            out_row[column] = mapped
                        writer.writerow(out_row)


def minimize_ids(input_path: Path, output_path: Path) -> None:
    entries, id_values = load_gtfs_zip(input_path)
    mappings = build_mapping(id_values)
    write_minimized_zip(entries, mappings, output_path)


def parse_args(argv: Iterable[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimize GTFS identifier strings for the specified feed ZIP.",
    )
    parser.add_argument("input", type=Path, help="Path to the source GTFS ZIP file.")
    parser.add_argument(
        "output",
        type=Path,
        help="Path where the minimized ZIP will be written.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] = None) -> None:
    args = parse_args(argv)
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")
    minimize_ids(args.input, args.output)


if __name__ == "__main__":
    main()
