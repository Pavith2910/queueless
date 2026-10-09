"""
evaluate.py - Step 10 evaluation.
  Part A: prediction accuracy (MAE, RMSE, bias, within 2 min)
  Part B: index performance (COLLSCAN vs IXSCAN with explain + timing)
  Part C: storage cost of indexes

Prints results and saves a report-ready file: evaluation_results.md
Run from project root:  python -m scripts.evaluate
"""
import statistics
import time
from datetime import datetime, timedelta

from db import db
from services.analytics_service import ensure_metrics_fresh

TZ = "Asia/Kolkata"
RUNS = 25            # each query is timed 25 times; we report the median
TRAIN_DAYS = 10      # historical baseline: train on first 10 days, test on the rest
lines = []           # collected markdown output


# ------------------------------------------------------------------ output helpers
def out(text=""):
    print(text)
    lines.append(text)


def table(headers, rows):
    out("| " + " | ".join(headers) + " |")
    out("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        out("| " + " | ".join(str(c) for c in row) + " |")
    out()


def r2(x):
    return "–" if x is None else round(x, 2)


def pct(x):
    return "–" if x is None else f"{x * 100:.1f}%"


# ------------------------------------------------------------------ Part A
# Adjusted formula = (N + 1) x S / C.  Since estimate = N x S / C,
# adjusted = estimate + estimate / N  (only when N > 0).
ADJUSTED = {"$cond": [
    {"$gt": ["$people_ahead", 0]},
    {"$add": ["$estimated_wait_min", {"$divide": ["$estimated_wait_min", "$people_ahead"]}]},
    0,
]}


def error_stats(prefix, prediction):
    """$group accumulators that measure the error of one prediction method."""
    err = {"$subtract": [prediction, "$actual_wait_min"]}
    return {
        f"{prefix}_mae": {"$avg": {"$abs": err}},
        f"{prefix}_mse": {"$avg": {"$pow": [err, 2]}},
        f"{prefix}_bias": {"$avg": err},
        f"{prefix}_within2": {"$avg": {"$cond": [{"$lte": [{"$abs": err}, 2]}, 1, 0]}},
    }


def accuracy_all_data():
    out("## A1. Prediction accuracy on all observations")
    out()
    fields = {
        "n": {"$sum": 1},
        "avg_actual": {"$avg": "$actual_wait_min"},
        **error_stats("f", "$estimated_wait_min"),
        **error_stats("a", ADJUSTED),
    }
    result = list(db.wait_observations.aggregate([
        {"$facet": {
            "overall": [{"$group": {"_id": "ALL", **fields}}],
            "by_location": [{"$group": {"_id": "$location_id", **fields}}, {"$sort": {"_id": 1}}],
            "by_queue_size": [{"$bucket": {
                "groupBy": "$people_ahead",
                "boundaries": [0, 1, 3, 6, 11, 21, 100000],
                "output": fields,
            }}],
        }},
    ]))[0]

    headers = ["Group", "Students", "Avg actual wait (min)",
               "Formula MAE", "Formula RMSE", "Formula bias", "Formula within ±2",
               "Adjusted MAE", "Adjusted bias", "Adjusted within ±2"]

    def row(label, g):
        return [label, f"{g['n']:,}", r2(g["avg_actual"]),
                r2(g["f_mae"]), r2(g["f_mse"] ** 0.5), r2(g["f_bias"]), pct(g["f_within2"]),
                r2(g["a_mae"]), r2(g["a_bias"]), pct(g["a_within2"])]

    out("**By location**")
    out()
    table(headers, [row(g["_id"], g) for g in result["by_location"]] +
          [row("**ALL**", result["overall"][0])])

    labels = {0: "0 ahead", 1: "1–2 ahead", 3: "3–5 ahead", 6: "6–10 ahead",
              11: "11–20 ahead", 21: "21+ ahead"}
    out("**By queue size when the student joined** (`$bucket`)")
    out()
    table(headers, [row(labels.get(g["_id"], g["_id"]), g) for g in result["by_queue_size"]])
    return result["overall"][0]


def accuracy_vs_history():
    out(f"## A2. Live formula vs historical average (train {TRAIN_DAYS} days, test the rest)")
    out()
    first = db.wait_observations.find_one(sort=[("joined_at", 1)])["joined_at"]
    split = first + timedelta(days=TRAIN_DAYS)
    key = {"$concat": ["$location_id", "|",
                       {"$toString": {"$hour": {"date": "$joined_at", "timezone": TZ}}}]}

    # TRAIN: average actual wait per (location, hour) -> temporary collection via $out
    list(db.wait_observations.aggregate([
        {"$match": {"joined_at": {"$lt": split}}},
        {"$group": {"_id": key, "avg_actual": {"$avg": "$actual_wait_min"}}},
        {"$out": "eval_baseline"},
    ]))

    # TEST: compare all three methods on unseen days
    groups = list(db.wait_observations.aggregate([
        {"$match": {"joined_at": {"$gte": split}}},
        {"$set": {"key": key}},
        {"$lookup": {"from": "eval_baseline", "localField": "key",
                     "foreignField": "_id", "as": "b"}},
        {"$set": {"hist": {"$ifNull": [{"$first": "$b.avg_actual"}, 0]}}},
        {"$group": {"_id": "$location_id", "n": {"$sum": 1},
                    **error_stats("f", "$estimated_wait_min"),
                    **error_stats("a", ADJUSTED),
                    **error_stats("h", "$hist")}},
        {"$sort": {"_id": 1}},
    ]))
    db.drop_collection("eval_baseline")

    total = sum(g["n"] for g in groups)
    overall = {"_id": "**ALL**", "n": total}
    for m in ("f", "a", "h"):
        for s in ("mae", "within2"):
            overall[f"{m}_{s}"] = sum(g[f"{m}_{s}"] * g["n"] for g in groups) / total

    table(["Location", "Test students",
           "Formula MAE", "Adjusted MAE", "Historical MAE",
           "Formula within ±2", "Adjusted within ±2", "Historical within ±2"],
          [[g["_id"], f"{g['n']:,}", r2(g["f_mae"]), r2(g["a_mae"]), r2(g["h_mae"]),
            pct(g["f_within2"]), pct(g["a_within2"]), pct(g["h_within2"])]
           for g in groups + [overall]])
    return overall


# ------------------------------------------------------------------ Part B
def median_ms(run):
    times = []
    for _ in range(RUNS):
        start = time.perf_counter()
        run()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def measure(coll, flt, sort, hint):
    def make_cursor():
        cur = db[coll].find(flt, {"_id": 0})
        if sort:
            cur = cur.sort(sort)
        return cur.hint(hint)

    plan = make_cursor().explain()
    stats = plan["executionStats"]
    stage = "IXSCAN" if "IXSCAN" in str(plan["queryPlanner"]) else "COLLSCAN"
    return {
        "stage": stage,
        "returned": stats["nReturned"],
        "docs": stats["totalDocsExamined"],
        "keys": stats["totalKeysExamined"],
        "ms": median_ms(lambda: list(make_cursor())),
    }


def index_benchmark():
    out(f"## B. Index performance (median of {RUNS} runs)")
    out()
    latest = db.queue_events.find_one(sort=[("timestamp", -1)])["timestamp"]
    obs_latest = db.wait_observations.find_one(sort=[("joined_at", -1)])["joined_at"]
    cases = [
        ("Q1 Trend: one location, last 24 h", "queue_events",
         {"location_id": "CANTEEN_A", "timestamp": {"$gte": latest - timedelta(hours=24)}},
         [("timestamp", 1)], "loc_time"),
        ("Q2 One location, last 7 days", "queue_events",
         {"location_id": "OFFICE_A", "timestamp": {"$gte": latest - timedelta(days=7)}},
         [("timestamp", 1)], "loc_time"),
        ("Q3 All events of one location", "queue_events",
         {"location_id": "LIBRARY"}, None, "loc_time"),
        ("Q4 Wait history: one location, last 24 h", "wait_observations",
         {"location_id": "CANTEEN_A", "joined_at": {"$gte": obs_latest - timedelta(hours=24)}},
         [("joined_at", 1)], "loc_joined"),
        ("Q5 Heatmap metrics: one location", "service_metrics",
         {"location_id": "CANTEEN_A"}, [("day_of_week", 1), ("hour", 1)], "uniq_loc_day_hour"),
    ]

    # Q6: an index on a LOW-selectivity field (only 3 possible values)
    db.queue_events.create_index("event_type", name="tmp_event_type")
    cases.append(("Q6 All service completions (low-selectivity index)", "queue_events",
                  {"event_type": "service_completed"}, None, "tmp_event_type"))

    rows, speedups = [], []
    for label, coll, flt, sort, index in cases:
        scan = measure(coll, flt, sort, [("$natural", 1)])
        idx = measure(coll, flt, sort, index)
        speedup = scan["ms"] / idx["ms"] if idx["ms"] > 0 else float("inf")
        speedups.append((label, speedup))
        rows.append([label, coll, f"{idx['returned']:,}",
                     f"{scan['docs']:,}", f"{idx['keys']:,} / {idx['docs']:,}",
                     f"{scan['ms']:.2f}", f"{idx['ms']:.2f}", f"{speedup:.1f}x"])
    db.queue_events.drop_index("tmp_event_type")

    table(["Query", "Collection", "Returned",
           "COLLSCAN docs examined", "IXSCAN keys / docs examined",
           "COLLSCAN ms", "IXSCAN ms", "Speed-up"], rows)
    return speedups


# ------------------------------------------------------------------ Part C
def storage_cost():
    out("## C. Storage cost of indexes (`$collStats`)")
    out()
    rows = []
    for coll in ["locations", "queue_status", "queue_events", "service_metrics", "wait_observations"]:
        s = list(db[coll].aggregate([{"$collStats": {"storageStats": {}}}]))[0]["storageStats"]
        indexes = ", ".join(f"{name} ({size / 1024:.0f} KB)" for name, size in s["indexSizes"].items())
        rows.append([coll, f"{s['count']:,}", f"{s['size'] / 1024:.0f} KB",
                     f"{s['totalIndexSize'] / 1024:.0f} KB", indexes])
    table(["Collection", "Documents", "Data size", "Total index size", "Indexes"], rows)


# ------------------------------------------------------------------ main
def main():
    ensure_metrics_fresh()
    out("# QueueLess - Evaluation Results")
    out()
    out(f"Generated: {datetime.now():%Y-%m-%d %H:%M}  ·  "
        f"queue_events: {db.queue_events.count_documents({}):,}  ·  "
        f"wait_observations: {db.wait_observations.count_documents({}):,}")
    out()

    overall = accuracy_all_data()
    test = accuracy_vs_history()
    speedups = index_benchmark()
    storage_cost()

    out("## Key findings")
    out()
    out(f"- Basic formula: MAE **{overall['f_mae']:.2f} min**, bias {overall['f_bias']:+.2f} min, "
        f"{overall['f_within2'] * 100:.1f}% of predictions within ±2 min.")
    out(f"- Adjusted formula: MAE **{overall['a_mae']:.2f} min**, bias {overall['a_bias']:+.2f} min, "
        f"{overall['a_within2'] * 100:.1f}% within ±2 min.")
    out(f"- On unseen test days: formula MAE {test['f_mae']:.2f}, adjusted {test['a_mae']:.2f}, "
        f"historical average {test['h_mae']:.2f} min.")
    best_label, best = max(speedups, key=lambda x: x[1])
    worst_label, worst = min(speedups, key=lambda x: x[1])
    out(f"- Largest index speed-up: {best_label} ({best:.1f}x). "
        f"Smallest: {worst_label} ({worst:.1f}x).")

    with open("evaluation_results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\nSaved: evaluation_results.md")


if __name__ == "__main__":
    main()