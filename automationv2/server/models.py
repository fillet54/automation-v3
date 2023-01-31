from flask import  current_app, g
from ..repository import RequirementsRepository

def get_db():
    if 'db' not in g:
        g.db = RequirementsRepository(current_app.config['DB_PATH'])
    return g.db