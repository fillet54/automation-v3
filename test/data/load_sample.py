import click
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pathlib import Path
from automationv3.models.requirements2 import Requirement

SAMPLE_DATA_PATH = Path(__file__).resolve().parent / 'sample_requirements.txt'


@click.command()
@click.option('--dbpath', default='./automationv3.db', help='Path to database file')
@click.option('--data', default=SAMPLE_DATA_PATH, help='Path to database file')
def load_sample(dbpath, data):
    engine = create_engine(f'sqlite:///{dbpath}')

    def line_to_requirement(line):
        line = line.strip()
        idx = line.rfind("[")
        requirement_text = line[:idx].strip()
        requirement_id = line[idx + 1:-2].strip()
        subsystem = requirement_id.split("VMC")[1].split("0")[0].strip()
        return Requirement(
            id=requirement_id, 
            text=requirement_text, 
            subsystem=subsystem
        )

    with (
        open(data, 'r') as file,
        Session(engine) as session
    ):
        requirements = [line_to_requirement(line)
                        for line in file]
        session.add_all(requirements)
        session.commit()

load_sample()

