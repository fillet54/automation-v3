"""Load Database with Sample Data

This script imports the sample DOORS history (test/data/doors) into a
database: it writes each run of the history as an export folder, then
imports them in order, as `automation-v3 requirements import` would.

Usage:
    load_sample.py [--dbpath=FILE] [--exports=DIR]
    load_sample.py (-h | --help)

Options:
    --dbpath=FILE    sqlite3 database file to load
                     [default: automationv3.db]
    --exports=DIR    where to write the export folders
                     [default: exports]

"""
from docopt import docopt

from automationv3.demo import load_requirements, write_sample_exports


def load_sample():
    args = docopt(__doc__)
    load_requirements(args['--dbpath'], write_sample_exports(args['--exports']))


if __name__ == '__main__':
    load_sample()
