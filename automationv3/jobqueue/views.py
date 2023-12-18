"""Job Runner / Queue"""

from pathlib import Path
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta

from . import sqlqueue
from .models import Worker
from ..database import get_db, db

jobqueue = Blueprint(
    "jobqueue", __name__, template_folder=Path(__file__).resolve().parent / "templates"
)


@jobqueue.route("/", methods=["GET"])
def list():
    q = sqlqueue.SQLPriorityQueue(get_db())

    q.put("Task 1")

    return render_template("queue.html", queue=q)


@jobqueue.route("/workers", methods=["POST"])
def register_worker():
    data = request.json
    worker_url = data.get("url")  # TODO: Validate url
    worker_status = data.get("status", "available")

    if not worker_url:
        return jsonify({"error": "Worker name is required"}), 400
    if worker_status not in Worker.ALLOWED_STATUS:
        return jsonify({"error": f"Status must be one of {Worker.ALLOWED_STATUS}"}), 400

    with db.session as session:
        worker = session.query(Worker).filter_by(url=worker_url).first()

        # keepalive and/or status update
        if worker:
            worker.last_keepalive = datetime.utcnow()
            worker.status = worker_status
            session.commit()

        # new worker
        else:
            new_worker = Worker(url=worker_url, status=worker_status)
            session.add(new_worker)
            session.commit()

    return "OK!", 200


@jobqueue.route("/workers", methods=["GET"])
def list_workers():
    show = request.args.get("show")
    show_all = show and show == "all"
    hx_request = request.headers.get("HX-Request", False)

    now = datetime.utcnow()
    five_minutes_ago = now - timedelta(minutes=5)

    with db.session as session:
        if show_all:
            workers = session.query(Worker).all()
        else:
            workers = (
                session.query(Worker)
                .filter(Worker.last_keepalive >= five_minutes_ago)
                .all()
            )

        if hx_request or "text/html" in request.headers.get("Accept", ""):
            return render_template(
                "workers.html",
                workers=workers,
                show_all=(None if show_all else "all"),
                missing_time=five_minutes_ago,
                hx_request=request.headers.get("HX-Request", False),
            )
        else:
            return jsonify(
                [
                    {
                        "id": worker.id,
                        "url": worker.url,
                        "status": worker.status,
                        "last_keepalive": worker.last_keepalive,
                    }
                    for worker in workers
                ]
            )


@jobqueue.app_template_filter()
def humanize_ts(timestamp=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    now = datetime.utcnow()
    try:
        diff = now - timestamp
    except TypeError:
        diff = now - datetime.fromtimestamp(timestamp)
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(int(second_diff)) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(int(second_diff / 60)) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(int(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(int(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(int(day_diff / 30)) + " months ago"
    return str(int(day_diff / 365)) + " years ago"
