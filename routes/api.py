"""
api.py - JSON API endpoints. Routes stay thin: they call services and return JSON.
"""
from flask import Blueprint, jsonify , request
from pymongo.errors import PyMongoError

from config import Config
from db import db, ping
from services.queue_service import get_all_queues, get_queue, now_ist
from services.recommend_service import recommend, RecommendError

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/health")
def health():
    ping()
    return jsonify(status="ok", database=Config.DB_NAME,
                   collections=db.list_collection_names())


@api.get("/queues")
def list_queues():
    queues = get_all_queues()
    return jsonify(generated_at=now_ist().isoformat(), demo_time=Config.DEMO_TIME or None,
        count=len(queues), queues=queues)


@api.get("/queues/<location_id>")
def queue_detail(location_id):
    queue = get_queue(location_id.upper())
    if queue is None:
        return jsonify(error=f"Location '{location_id}' not found"), 404
    return jsonify(queue)

@api.get("/recommend/<location_id>")
def recommend_route(location_id):
    service = request.args.get("service") or None
    try:
        return jsonify(recommend(location_id.upper(), service))
    except RecommendError as e:
        return jsonify(error=str(e)), 400

@api.errorhandler(PyMongoError)
def database_error(e):
    """Any MongoDB problem returns a clean JSON error instead of crashing."""
    return jsonify(status="error", message="Database error", detail=str(e)), 503