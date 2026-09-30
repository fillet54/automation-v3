import threading
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

worker_status = "available"


def send_keep_alive_message():
    """Registers with the central server, or refreshes an existing registration"""
    return requests.post(
        app.config["WORKER_URL"],
        json={"url": app.config["SELF_URL"], "status": worker_status},
    )


def register_worker():
    response = send_keep_alive_message()
    if response.status_code == 200:
        print("Registration successful")
        keep_alive_thread = threading.Thread(target=send_keep_alive_forever)
        keep_alive_thread.daemon = True
        keep_alive_thread.start()


def send_keep_alive_forever():
    while True:
        # Send keep-alive message
        send_keep_alive_message()
        time.sleep(60)  # Keep-alive every 60 seconds


def update_status(new_status):
    global worker_status
    worker_status = new_status
    send_keep_alive_message()


@app.route("/submit-job", methods=["POST"])
def submit_job():
    if worker_status != "available":
        return jsonify({"status": "Work is current busy. Job not started"}), 503

    job_data = request.json
    update_status("busy")
    job_thread = threading.Thread(target=process_job, args=(job_data,))
    job_thread.daemon = True
    job_thread.start()
    return jsonify({"status": "Job submitted"}), 202


def process_job(job_data):
    # Implement job processing logic here
    print("Executing", job_data)
    time.sleep(20)
    print("Job Complete")
    update_status("available")


@app.route("/")
def index():
    return "Worker Service Running"
