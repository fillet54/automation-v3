Requirements documents
======================

.. rst-class:: lead

   Requirements are written in reStructuredText, one directive per
   requirement, so a requirement can hold lists, emphasis and notes.

The format
----------

A requirements document is an ordinary ``.rst`` file. Headings and prose are
documentation; each ``requirement`` directive is a requirement, with its id
as the argument and its text as the content:

.. code-block:: rst

   Electrical power
   ================

   .. requirement:: VM-EPS-002

      The VM shall shed loads in the order of the load shedding table when
      the battery state of charge falls below each of the following
      thresholds:

      - 60%: the payload;
      - 50%: the non-essential heaters;
      - 40%: everything except the essential loads.

The subsystem, which groups requirements on the Requirements page, is the
``:subsystem:`` option if one is given, otherwise the middle part of a
three-part id (``VM-EPS-002`` is ``EPS``), otherwise the part before the
first dash. An id may appear only once.

Pages show the text rendered, with each "shall" marked with the
requirement's id, and scripts reference it with ``:req:`VM-EPS-002```.

Loading requirements
--------------------

``test/data/load_sample.py`` loads requirements into the database:

.. code-block:: bash

   python test/data/load_sample.py --dbpath automationv3.db \
       --data requirements/vehicle_manager.rst --data more.rst

Without ``--data`` it loads the samples: every ``.rst`` document in
``test/data/requirements`` and the older one-per-line file,
``test/data/sample_requirements.txt``, whose lines end in their id in
brackets.

The sample set
--------------

``test/data/requirements/vehicle_manager.rst`` is a realistic sample written
for this project: 64 requirements for the Vehicle Manager of a satellite
platform, in ten subsystems. Its tests, written as :doc:`flows of TBD steps
<../scripts/planning>`, are in the sample set's ``VM`` folder.
