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

from contextlib import closing

from docopt import docopt 

from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models
from automationv3.demo import parse_requirement

SAMPLE_DATA_PATH = Path(__file__).resolve().parent / 'sample_requirements.txt'

def load_sample():

    args = docopt(__doc__)

    dbpath = args['--dbpath']
    data = args['--data']

    with (
        open(data, 'r') as file,
        closing(connect(dbpath)) as conn
    ):
        init_db(conn)
        models.insert(conn, [parse_requirement(line) for line in file if line.strip()])

if __name__ == '__main__':
    load_sample()

