"""
analytics_api.py - Read-only analytics endpoints.
"""
from flask import Blueprint, jsonify

from services import analytics_service as analytics

analytics_api = Blueprint("analytics_api", __name__, url_prefix="/api/analytics")


@analytics_api.get("/overview")
def overview():
    return jsonify(analytics.overview())


@analytics_api.get("/hourly")
def hourly():
    return jsonify(analytics.hourly_peaks())


@analytics_api.get("/service-speed")
def service_speed():
    return jsonify(analytics.service_speed())


@analytics_api.get("/heatmap/<location_id>")
def heatmap(location_id):
    return jsonify(analytics.heatmap(location_id.upper()))


@analytics_api.get("/forecast/<location_id>")
def forecast(location_id):
    result = analytics.forecast(location_id.upper())
    if result is None:
        return jsonify(error="Location not found"), 404
    return jsonify(result)


@analytics_api.post("/refresh")
def refresh():
    return jsonify(analytics.refresh_service_metrics())