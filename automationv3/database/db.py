from flask import  current_app, g, abort
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class DatabaseHelper:
    @property
    def session(self):
        if g:
            if 'session' not in g:
                g.session = current_app.config['DB_SESSION_MAKER']()
            return g.session
        else:
            return sessionmaker(create_engine(f'sqlite:///{get_connection_str()}')) 

    def query(self, *args):
        return self.session.query(*args)

db = DatabaseHelper()

def get_connnection_str():
    # somehow get path to db. For now just hardcode
    return './automationv3.db'

def get_db():
    if g:
        if 'sqlite_db' not in g:
            g.sqlite_db = sqlite3.connect(current_app.config['DB_PATH'])
        return g.sqlite_db
    else:
        return sqlite3.connect(get_connnection_str())
