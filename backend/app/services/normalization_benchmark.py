from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

from app.services.mapping import normalize_match_key


@dataclass(frozen=True)
class SyntheticInventoryRow:
    assignment_group: str
    business_service_ci_name: str
    scope_status: str
    functional_track: str
    service_type: str
    service_entitlement: str


def build_synthetic_inventory() -> list[SyntheticInventoryRow]:
    rows: list[SyntheticInventoryRow] = []
    for group_index in range(40):
        scope_status = "in_scope" if group_index < 30 else "out_of_scope"
        for service_index in range(8):
            rows.append(
                SyntheticInventoryRow(
                    assignment_group=f"IT-NSA-BENCH-GROUP-{group_index:02d}",
                    business_service_ci_name=(
                        f"Benchmark Service {group_index:02d}-{service_index:02d}"
                    ),
                    scope_status=scope_status,
                    functional_track=f"Track {group_index % 6}",
                    service_type=["Integrator", "End-to-end", "Archived"][service_index % 3],
                    service_entitlement=["Gold", "Silver", "Bronze"][service_index % 3],
                )
            )
    return rows


def unique_value(values: list[str]) -> str | None:
    normalized = {normalize_match_key(value): value for value in values if value.strip()}
    return next(iter(normalized.values())) if len(normalized) == 1 else None


def run_benchmark(rows: int, pipeline: str) -> None:
    if pipeline.lower() != "v2":
        raise SystemExit("This synthetic benchmark only exercises the v2 design.")

    timings: dict[str, float] = {}
    started_at = perf_counter()

    stage_started = perf_counter()
    inventory = build_synthetic_inventory()
    timings["generate_synthetic_inventory"] = perf_counter() - stage_started

    stage_started = perf_counter()
    in_scope_groups = {
        normalize_match_key(row.assignment_group)
        for row in inventory
        if row.scope_status == "in_scope"
    }
    by_group: dict[str, list[SyntheticInventoryRow]] = defaultdict(list)
    by_group_service: dict[tuple[str, str], SyntheticInventoryRow] = {}
    for row in inventory:
        group_key = normalize_match_key(row.assignment_group)
        service_key = normalize_match_key(row.business_service_ci_name)
        if group_key is None or service_key is None:
            continue
        by_group[group_key].append(row)
        by_group_service.setdefault((group_key, service_key), row)
    group_functional_tracks = {
        group_key: unique_value([row.functional_track for row in group_rows])
        for group_key, group_rows in by_group.items()
    }
    timings["build_reference_indexes"] = perf_counter() - stage_started

    stage_started = perf_counter()
    in_scope_count = 0
    out_of_scope_count = 0
    enriched_count = 0
    for index in range(rows):
        group_index = index % 45
        service_index = index % 10
        assignment_group = f"IT-NSA-BENCH-GROUP-{group_index:02d}"
        business_service = f"Benchmark Service {group_index:02d}-{service_index:02d}"
        group_key = normalize_match_key(assignment_group)
        service_key = normalize_match_key(business_service)
        if group_key in in_scope_groups:
            in_scope_count += 1
        else:
            out_of_scope_count += 1
        if group_key is not None and service_key is not None:
            if (group_key, service_key) in by_group_service:
                enriched_count += 1
            elif group_functional_tracks.get(group_key):
                enriched_count += 1
    timings["normalize_scope_and_enrich_rows"] = perf_counter() - stage_started

    stage_started = perf_counter()
    chunk_size = 2000
    chunks = (rows + chunk_size - 1) // chunk_size
    timings["plan_bulk_delete_insert_chunks"] = perf_counter() - stage_started

    duration = perf_counter() - started_at
    print("Synthetic V2 normalization/apply-mapping benchmark")
    print(f"rows={rows}")
    print(f"in_scope_rows={in_scope_count}")
    print(f"out_of_scope_rows={out_of_scope_count}")
    print(f"enriched_rows={enriched_count}")
    print(f"bulk_chunks={chunks}")
    print(f"duration_seconds={duration:.4f}")
    print(f"rows_per_second={rows / duration:.2f}")
    for stage, seconds in timings.items():
        print(f"{stage}={seconds:.4f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=8000)
    parser.add_argument("--pipeline", choices=["v2"], default="v2")
    args = parser.parse_args()
    run_benchmark(args.rows, args.pipeline)


if __name__ == "__main__":
    main()
