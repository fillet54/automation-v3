"""Load Database with Sample Data

This script will load a supplied database with sample
requirements

Usage:
    load_sample.py [--dbpath=FILE] [--data=FILE]
    load_sample.py (-h | --help)

Options:
    --dbpath=FILE    sqlite3 database file to load
                     [default: automationv3.db]
    --data=FILE      path to text file containing
                     requirements to load. Each 
                     requirement on its ownline with
                     id at end of each line surrounded 
                     by '[]'
                     [default: test/data/sample_requirements.txt]
 

"""
from pathlib import Path

from docopt import docopt 
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from automationv3.requirements.models import Requirement

SAMPLE_DATA_PATH = Path(__file__).resolve().parent / 'sample_requirements.txt'

def load_sample():

    args = docopt(__doc__)

    dbpath = args['--dbpath']
    data = args['--data']

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

if __name__ == '__main__':
    load_sample()

