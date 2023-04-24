import click
from pathlib import Path
from waitress import serve
from . import app


@click.command()
@click.option('--port', default=8080, help="HTTP port number")
@click.option('--dbpath', default='./requirements.db', help="HTTP port number")
def start_server(port, dbpath):
    print(f"""\
                _                        _   _              __      ______  
     /\        | |                      | | (_)             \ \    / /___ \ 
    /  \  _   _| |_ ___  _ __ ___   __ _| |_ _  ___  _ __    \ \  / /  __) |
   / /\ \| | | | __/ _ \| '_ ` _ \ / _` | __| |/ _ \| '_ \    \ \/ /  |__ < 
  / ____ \ |_| | || (_) | | | | | | (_| | |_| | (_) | | | |    \  /   ___) |
 /_/    \_\__,_|\__\___/|_| |_| |_|\__,_|\__|_|\___/|_| |_|     \/   |____/ 

                                                             Version: 3.0.0
----------------------------------------------------------------------------

    Server started: http://localhost:{port}/

    """)

    app.config['DB_PATH'] = Path(dbpath).resolve()
    serve(app, port=port)


start_server()


