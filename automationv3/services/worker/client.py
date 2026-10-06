"""The central server's job API over HTTP, as one worker sees it"""

import base64

import requests


class ServerClient:
    def __init__(self, server_url, worker_url, session=None):
        self.server_url = server_url.rstrip("/")
        self.worker_url = worker_url
        self.session = session or requests.Session()

    def _post(self, path, **data):
        return self.session.post(
            f"{self.server_url}/runner{path}",
            json={"worker_url": self.worker_url, **data},
        )

    def check_in(self, status, capabilities, started=False):
        response = self.session.post(
            f"{self.server_url}/runner/workers",
            json={"url": self.worker_url, "status": status, "started": started,
                  **capabilities},
        )
        return response.status_code == 200

    def pending_jobs(self):
        response = self.session.get(
            f"{self.server_url}/runner/jobs?worker_url={self.worker_url}"
        )
        response.raise_for_status()
        return response.json()

    def claim(self, job_id):
        response = self._post(f"/jobs/{job_id}/claim")
        return response.json() if response.status_code == 200 else None

    def start(self, job_id):
        self._post(f"/jobs/{job_id}/start")

    def release(self, job_id):
        self._post(f"/jobs/{job_id}/release")

    def post_events(self, job_id, events):
        self._post(f"/jobs/{job_id}/events", events=events)

    def attach(self, job_id, name, data):
        """Store a file with the job's run; returns the name it was stored as"""
        response = self._post(f"/jobs/{job_id}/files", name=name,
                              data=base64.b64encode(data).decode())
        response.raise_for_status()
        return response.json()["name"]

    def complete(self, job_id, outcome, **details):
        self._post(f"/jobs/{job_id}/complete", outcome=outcome, **details)
