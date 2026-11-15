"""The requirements the language server answers from, read from the
application database: the ones the scripts root's workspace verifies
(services/requirements/models.py: workspace_context)"""

import time
from contextlib import closing
from pathlib import Path

LISTED_FOR = 30  # seconds a listing is kept


class DatabaseRequirements:
    def __init__(self, dbpath, root):
        self.dbpath, self.root = Path(dbpath), Path(root)
        self.listed, self.at = [], None

    def all(self):
        """Every requirement in the context, [] if there is no database"""
        from ..services.database import connect
        from ..services.requirements import models
        now = time.monotonic()
        if self.at is None or now - self.at > LISTED_FOR:
            self.at = now
            try:
                with closing(connect(self.dbpath)) as conn:
                    context, _ = models.workspace_context(conn, self.root)
                    self.listed = models.find_all(conn, context=context)
            except Exception:
                self.listed = []
        return self.listed

    def find(self, id):
        return next((r for r in self.all() if r.id == id), None)


def beside(dbpath):
    """What to give Server as `requirements`: the database at `dbpath`
    if there is one, read for whichever root the server is given"""
    def requirements(root):
        return DatabaseRequirements(dbpath, root) if Path(dbpath).is_file() else None
    return requirements
