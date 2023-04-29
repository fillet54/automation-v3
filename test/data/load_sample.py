import click
import sqlite3
from pathlib import Path
from automationv3.models import Requirements, import_requirements_from_file

SAMPLE_DATA_PATH = Path(__file__).resolve().parent / 'sample_requirements.txt'


@click.command()
@click.option('--dbpath', default='requirements.db', help='Path to database file')
@click.option('--data', default=SAMPLE_DATA_PATH, help='Path to database file')
def load_sample(dbpath, data):
    conn = sqlite3.connect(dbpath)
    repo = Requirements(conn)
    import_requirements_from_file(data, repo)

load_sample()

