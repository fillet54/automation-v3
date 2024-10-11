from pathlib import Path

from flask import Flask, g, redirect, url_for, render_template

from .workspace import workspace

app = Flask(__name__)
app.register_blueprint(workspace, url_prefix="/workspace")

@app.route("/")
def index():
    return render_template(
        "index.html"
    )


@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


if __name__ == "__main__":

    # for now just hardcode config
    app.config["data_path"] = Path("~") / ".automationv3"
    app.config["workspace_root"] = Path(__file__).resolve().parents[2] / "test" / "data" / "git_repos"

    # setup
    app.config["data_path"].mkdir(parents=True, exist_ok=True)

    app.run(port=8097, debug=True)
