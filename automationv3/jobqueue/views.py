'''Job Runner / Queue'''

from pathlib import Path
from flask import Blueprint, render_template, request, abort, jsonify
from datetime import datetime 

from . import sqlqueue
from .models import Worker
from ..database import get_db, db

jobqueue = Blueprint('jobqueue', __name__, 
                   template_folder=Path(__file__).resolve().parent / 'templates')

@jobqueue.route("/", methods=["GET"])
def list():
    q = sqlqueue.SQLPriorityQueue(get_db())

    q.put('Task 1')

    return render_template("queue.html", queue=q)


@jobqueue.route("/workers", methods=['POST'])
def register_worker():
    data = request.json
    worker_url = data.get('url') # TODO: Validate url
    worker_status = data.get('status', 'available')

    if not worker_url:
        return jsonify({'error': 'Worker name is required'}), 400
    if worker_status not in Worker.ALLOWED_STATUS:
        return jsonify({'error': f'Status must be one of {Worker.ALLOWED_STATUS}'}), 400

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

    return 'OK!', 200

@jobqueue.route("/workers", methods=['GET'])
def list_worker():
    with db.session as session:
        workers = session.query(Worker).all()

        if 'text/html' in request.headers.get('Accept', ''):
            return render_template('workers.html', workers=workers)
        else:
            return jsonify([{'id': worker.id, 
                             'url': worker.url, 
                             'status': worker.status, 
                             'last_keepalive': worker.last_keepalive} 
                            for worker in workers])


