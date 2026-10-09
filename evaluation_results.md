# QueueLess - Evaluation Results

Generated: 2026-10-09 22:20  ·  queue_events: 57,362  ·  wait_observations: 46,570

## A1. Prediction accuracy on all observations

**By location**

| Group | Students | Avg actual wait (min) | Formula MAE | Formula RMSE | Formula bias | Formula within ±2 | Adjusted MAE | Adjusted bias | Adjusted within ±2 |
|---|---|---|---|---|---|---|---|---|---|
| CANTEEN_A | 10,755 | 1.79 | 0.25 | 0.52 | -0.15 | 98.7% | 0.24 | -0.01 | 99.0% |
| CANTEEN_B | 7,613 | 0.18 | 0.08 | 0.2 | -0.06 | 100.0% | 0.09 | -0.01 | 100.0% |
| LIBRARY | 12,811 | 0.25 | 0.09 | 0.2 | -0.07 | 100.0% | 0.09 | -0.02 | 100.0% |
| OFFICE_A | 1,781 | 4.67 | 1.23 | 1.88 | -0.88 | 77.4% | 1.22 | 0.14 | 75.9% |
| OFFICE_B | 2,861 | 6.72 | 1.02 | 1.59 | -0.54 | 82.7% | 1.03 | 0.22 | 83.4% |
| SNACK_KIOSK | 10,749 | 0.76 | 0.21 | 0.37 | -0.16 | 99.9% | 0.21 | -0.02 | 99.9% |
| **ALL** | 46,570 | 1.28 | 0.25 | 0.63 | -0.17 | 97.7% | 0.25 | 0.01 | 97.8% |

**By queue size when the student joined** (`$bucket`)

| Group | Students | Avg actual wait (min) | Formula MAE | Formula RMSE | Formula bias | Formula within ±2 | Adjusted MAE | Adjusted bias | Adjusted within ±2 |
|---|---|---|---|---|---|---|---|---|---|
| 0 ahead | 33,951 | 0.09 | 0.09 | 0.28 | -0.09 | 99.7% | 0.09 | -0.09 | 99.7% |
| 1–2 ahead | 5,953 | 1.14 | 0.44 | 0.71 | -0.34 | 97.1% | 0.43 | 0.25 | 97.6% |
| 3–5 ahead | 2,698 | 3.12 | 0.66 | 1.1 | -0.34 | 94.0% | 0.74 | 0.39 | 90.9% |
| 6–10 ahead | 1,605 | 6.26 | 0.96 | 1.49 | -0.43 | 87.0% | 0.96 | 0.34 | 87.6% |
| 11–20 ahead | 1,292 | 10.89 | 1.2 | 1.69 | -0.72 | 82.7% | 1.03 | -0.05 | 88.4% |
| 21+ ahead | 1,071 | 16.07 | 1.15 | 1.53 | -0.29 | 84.6% | 1.14 | 0.26 | 84.8% |

## A2. Live formula vs historical average (train 10 days, test the rest)

| Location | Test students | Formula MAE | Adjusted MAE | Historical MAE | Formula within ±2 | Adjusted within ±2 | Historical within ±2 |
|---|---|---|---|---|---|---|---|
| CANTEEN_A | 4,033 | 0.24 | 0.23 | 1.37 | 99.3% | 99.7% | 75.7% |
| CANTEEN_B | 2,827 | 0.08 | 0.09 | 0.22 | 100.0% | 100.0% | 99.9% |
| LIBRARY | 6,121 | 0.14 | 0.13 | 0.44 | 100.0% | 100.0% | 95.0% |
| OFFICE_A | 772 | 1.26 | 1.3 | 3.21 | 78.1% | 74.4% | 45.1% |
| OFFICE_B | 1,218 | 1.0 | 1.11 | 4.8 | 84.3% | 81.9% | 40.0% |
| SNACK_KIOSK | 4,197 | 0.22 | 0.24 | 0.68 | 99.9% | 99.9% | 91.1% |
| **ALL** | 19,168 | 0.27 | 0.28 | 1.04 | 97.9% | 97.7% | 85.3% |

## B. Index performance (median of 25 runs)

| Query | Collection | Returned | COLLSCAN docs examined | IXSCAN keys / docs examined | COLLSCAN ms | IXSCAN ms | Speed-up |
|---|---|---|---|---|---|---|---|
| Q1 Trend: one location, last 24 h | queue_events | 925 | 57,362 | 925 / 925 | 138.36 | 9.93 | 13.9x |
| Q2 One location, last 7 days | queue_events | 1,368 | 57,362 | 1,368 / 1,368 | 69.95 | 14.93 | 4.7x |
| Q3 All events of one location | queue_events | 15,129 | 57,362 | 15,129 / 15,129 | 149.63 | 131.72 | 1.1x |
| Q4 Wait history: one location, last 24 h | wait_observations | 828 | 46,570 | 828 / 828 | 53.22 | 6.67 | 8.0x |
| Q5 Heatmap metrics: one location | service_metrics | 92 | 463 | 92 / 92 | 2.53 | 2.15 | 1.2x |
| Q6 All service completions (low-selectivity index) | queue_events | 46,607 | 57,362 | 46,607 / 46,607 | 261.45 | 326.44 | 0.8x |

## C. Storage cost of indexes (`$collStats`)

| Collection | Documents | Data size | Total index size | Indexes |
|---|---|---|---|---|
| locations | 6 | 2 KB | 80 KB | _id_ (20 KB), uniq_location_id (20 KB), by_group (20 KB), by_service (20 KB) |
| queue_status | 6 | 1 KB | 76 KB | _id_ (20 KB), uniq_status_location (20 KB), by_status (36 KB) |
| queue_events | 57,362 | 10257 KB | 1584 KB | _id_ (848 KB), loc_time (736 KB) |
| service_metrics | 463 | 82 KB | 72 KB | _id_ (36 KB), uniq_loc_day_hour (36 KB) |
| wait_observations | 46,570 | 7268 KB | 996 KB | _id_ (472 KB), loc_joined (524 KB) |

## Key findings

- Basic formula: MAE **0.25 min**, bias -0.17 min, 97.7% of predictions within ±2 min.
- Adjusted formula: MAE **0.25 min**, bias +0.01 min, 97.8% within ±2 min.
- On unseen test days: formula MAE 0.27, adjusted 0.28, historical average 1.04 min.
- Largest index speed-up: Q1 Trend: one location, last 24 h (13.9x). Smallest: Q6 All service completions (low-selectivity index) (0.8x).