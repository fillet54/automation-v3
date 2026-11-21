"""The central server's job API over HTTP, as one worker sees it"""

import base64

import requests

from ..client import normal_server
from .worker import JobLost


class ServerClient:
    """`token` is the worker token a central server issued (see the Admin
    page); a single-user server needs none."""

    def __init__(self, server_url, worker_url, session=None, token=None):
        self.server_url = normal_server(server_url)
        self.worker_url = worker_url
        self.session = session or requests.Session()
        self.token = token

    def _auth(self):
        return {"headers": {"Authorization": f"Bearer {self.token}"}} if self.token else {}

    def _held(self, job_id, response):
        """`response`, unless it failed: JobLost if the server says the
        job is gone or not this worker's (404, 409)"""
        if response.status_code in (404, 409):
            try:
                reason = (response.json() or {}).get("error", "")
            except ValueError:
                reason = ""
            raise JobLost(job_id, reason)
        response.raise_for_status()
        return response

    def _post(self, path, **data):
        return self.session.post(
            f"{self.server_url}/runner{path}",
            json={"worker_url": self.worker_url, **data},
            **self._auth(),
        )

    def check_in(self, status, capabilities, started=False):
        response = self.session.post(
            f"{self.server_url}/runner/workers",
            json={"url": self.worker_url, "status": status, "started": started,
                  **capabilities},
            **self._auth(),
        )
        if response.status_code in (401, 403):
            try:
                error = (response.json() or {}).get("error")
            except ValueError:
                error = None
            raise PermissionError(f"The server refused this worker: "
                                  f"{error or response.status_code}")
        return response.status_code == 200

    def pending_jobs(self):
        response = self.session.get(
            f"{self.server_url}/runner/jobs",
            params={"worker_url": self.worker_url},
            **self._auth(),
        )
        response.raise_for_status()
        return response.json()

    def claim(self, job_id):
        response = self._post(f"/jobs/{job_id}/claim")
        return response.json() if response.status_code == 200 else None

    def start(self, job_id):
        self._held(job_id, self._post(f"/jobs/{job_id}/start"))

    def release(self, job_id):
        self._held(job_id, self._post(f"/jobs/{job_id}/release"))

    def post_events(self, job_id, events):
        self._held(job_id, self._post(f"/jobs/{job_id}/events", events=events))

    def attach(self, job_id, name, data):
        """Store a file with the job's run; returns the name it was stored as"""
        response = self._post(f"/jobs/{job_id}/files", name=name,
                              data=base64.b64encode(data).decode())
        return self._held(job_id, response).json()["name"]

    def complete(self, job_id, outcome, **details):
        self._held(job_id, self._post(f"/jobs/{job_id}/complete", outcome=outcome, **details))
