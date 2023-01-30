from . import app
from waitress import serve

serve(app, port=5000)