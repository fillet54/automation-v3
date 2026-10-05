"""The worker's own HTTP interface: a status page

Optional: a worker runs the same with or without it.
"""

from flask import Flask, jsonify


def create_worker_app(worker):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return jsonify({
            "status": worker.status,
            **worker.host.capabilities(),
        })

    return app
