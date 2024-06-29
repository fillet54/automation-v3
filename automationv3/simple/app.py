from flask import Flask, g, redirect, url_for, render_template
import mimetypes

from .views import simple

# add support for rst mimetype
mimetypes.add_type("text/x-rst", ".rst")


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("home.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


# cleanup database connection
@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, "sqlite_db"):
        g.sqlite_db.close()

    if hasattr(g, "session"):
        g.session.close()
