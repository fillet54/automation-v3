from flask import  current_app, g
import sqlite3

from ..models import Requirements, Workspace

def get_db():
    if 'sqlite_db' not in g:
        g.sqlite_db = sqlite3.connect(current_app.config['DB_PATH'])
    return g.sqlite_db

def get_requirements():
    conn = get_db()
    return Requirements(conn)

def get_workspace(id=0):
    conn = get_db()
    root = current_app.config['WORKSPACE_PATH']
    return Workspace(id, conn, root)
