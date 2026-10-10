"""Aggregate event-paired article durations, excluding every between-article gap."""

import math


def reading_summary(rows, expected_count):
    rows = list(rows)
    if len(rows) != expected_count or any(r["status"] != "completed" for r in rows):
        raise ValueError("Reading speed requires all Condition 1 articles to be completed")
    modes = {r["count_mode"] for r in rows}
    if len(modes) != 1:
        raise ValueError("Cannot combine different count units")
    total_s = 0.0
    total_units = 0
    for row in rows:
        if not row["start_event_id"] or not row["end_event_id"]:
            raise ValueError("Missing paired article events")
        duration = row["end_timestamp_s"] - row["start_timestamp_s"]
        if not math.isfinite(duration) or duration <= 0 or row["unit_count"] <= 0:
            raise ValueError("Reading counts and durations must be positive")
        total_s += duration
        total_units += row["unit_count"]
    mode = modes.pop()
    return dict(article_count=len(rows), total_units=total_units, total_reading_s=total_s,
                count_mode=mode, speed_per_minute=60.0 * total_units / total_s,
                speed_unit="words/min" if mode == "words" else "hanzi/min",
                timing_source="psychopy_flip")
