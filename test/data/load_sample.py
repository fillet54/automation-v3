"""Load Database with Sample Data

This script will load a supplied database with sample
requirements

Usage:
    load_sample.py [--dbpath=FILE] [--data=FILE...]
    load_sample.py (-h | --help)

Options:
    --dbpath=FILE    sqlite3 database file to load
                     [default: automationv3.db]
    --data=FILE      a requirements file: an rst requirements
                     document (.rst, with a requirement directive
                     per requirement), or text with one requirement
                     per line and its id at the end in '[]'.
                     Repeat for several. By default, the sample
                     requirements: test/data/sample_requirements.txt
                     and test/data/requirements/*.rst

"""
from docopt import docopt

from automationv3.demo import load_requirements


def load_sample():
    args = docopt(__doc__)
    load_requirements(args['--dbpath'], args['--data'] or None)


if __name__ == '__main__':
    load_sample()
