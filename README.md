# QueueLess

A MongoDB-based smart queue monitoring, waiting-time estimation and analytics system.
NoSQL Databases course project.

## Tech stack
Python + Flask · MongoDB (PyMongo) · HTML/CSS/JavaScript · Chart.js

## Setup (Windows)
1. Install Python 3.11+, MongoDB Community Server and mongosh.
2. In the project folder:
```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
```
   Edit `.env` and set `STAFF_PIN` and `SECRET_KEY`.
3. Build the database (run in this order):
```
   python -m scripts.setup_db         # collections, validation, indexes, locations
   python -m scripts.add_walk_times   # walking times + multikey index
   python -m scripts.generate_data    # 14 days of simulated queue activity
```
4. Start the app: `python app.py` and open http://localhost:5000
5. Run the evaluation: `python -m scripts.evaluate` (writes evaluation_results.md)

## Pages
- `/` live dashboard · `/analytics` analytics · `/staff` staff panel (PIN)

## Collections
locations · queue_status (live) · queue_events (history) · service_metrics (cache) · wait_observations (ground truth)

## Demo clock
Set `DEMO_TIME=13:00` in `.env` to make the app behave as if it is 1 PM (a badge is shown on the dashboard). Leave it empty for real time.