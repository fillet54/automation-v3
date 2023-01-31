from waitress import serve
from . import app

app.config['DB_PATH'] = 'requirements.db'
serve(app, port=5000)