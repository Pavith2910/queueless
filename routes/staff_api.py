"""
staff_api.py - Write endpoints for staff. All require a logged-in staff session.
"""
from functools import wraps

from flask import Blueprint, jsonify, request, session

from services import staff_service as staff
from services.queue_service import get_queue

staff_api = Blueprint("staff_api", __name__, url_prefix="/api/staff")


def staff_required(view):
    """Blocks the request unless the staff member has logged in with the PIN."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_staff"):
            return jsonify(error="Staff login required"), 401
        return view(*args, **kwargs)
    return wrapper


def _int_field(name, low, high):
    """Reads a whole number from the JSON body and checks its range."""
    value = (request.get_json(silent=True) or {}).get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise staff.QueueError(f"'{name}' must be a whole number from {low} to {high}")
    return value


@staff_api.errorhandler(staff.QueueError)
def bad_request(e):
    return jsonify(error=str(e)), 400


@staff_api.post("/queues/<location_id>/join")
@staff_required
def join(location_id):
    location_id = location_id.upper()
    staff.add_people(location_id, _int_field("count", 1, 50))
    return jsonify(get_queue(location_id))


@staff_api.post("/queues/<location_id>/serve")
@staff_required
def serve(location_id):
    location_id = location_id.upper()
    staff.serve_next(location_id)
    return jsonify(get_queue(location_id))


@staff_api.post("/queues/<location_id>/set")
@staff_required
def set_count(location_id):
    location_id = location_id.upper()
    staff.set_waiting(location_id, _int_field("waiting", 0, 500))
    return jsonify(get_queue(location_id))


@staff_api.post("/queues/<location_id>/counters")
@staff_required
def counters(location_id):
    location_id = location_id.upper()
    staff.set_counters(location_id, _int_field("counters", 0, 10))
    return jsonify(get_queue(location_id))