import sys
import sqlite3
from flask import  current_app, g, abort

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class DatabaseHelper:
    def __init__(self):
        self._engine = None
        self._sessionmaker = None

    @property
    def engine(self):
        if g:
            if 'engine' not in g:
                g.engine = current_app.config['DB_ENGINE']()
            return g.engine
        else:
            if self._engine is None or 'unittest' in sys.modules:
                conn_str = f'sqlite:///{self.get_connection_str()}'
                self._engine = create_engine(conn_str)
            return self._engine

    @property
    def session(self):
        if g:
            if 'session' not in g:
                g.session = current_app.config['DB_SESSION_MAKER']()
            return g.session
        else:
            if self._sessionmaker is None or 'unittest' in sys.modules:
                self._sessionmaker = sessionmaker(self.engine)
            return self._sessionmaker()

    def get_connection_str(self):
        # TODO: somehow get path to db. For now just hardcode
        if 'unittest' in sys.modules:
            return 'test.db'
        else:
            return current_app.config['DB_PATH']


db = DatabaseHelper()

def get_db():
    if g:
        if 'sqlite_db' not in g:
            g.sqlite_db = sqlite3.connect(db.get_connection_str())
        return g.sqlite_db
    else:
        return sqlite3.connect(db.get_connection_str())
