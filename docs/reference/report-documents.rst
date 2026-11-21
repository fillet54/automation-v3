Report documents
================

.. rst-class:: lead

   A report's document is reStructuredText: prose, and directives where the
   report's data goes.

Every report has a document, ``report.rst`` in its folder. A report starts
from its workspace template's ``report.rst``. You can then edit it until the
report is frozen. The directives stay in it for good: they're resolved against
the report's data whenever the document is shown or built, and the data they
read travels with the report, so an exported bundle can always be built again.

Directives
----------

Each directive writes one part of the document, from a snippet of the same
name (below):

``.. report-identification::``
   What the report is: its id and name, its workspace, its runs, the UUT
   versions and environments they ran on, and the requirements context. An
   exported document adds when it was exported and its bundle.

``.. report-summary::``
   The outcome in a sentence (how many requirements fail, aren't fully
   verified, have no tests and pass, and how many scripts ran on which
   versions), the requirements by verdict, and how a verdict is judged.

``.. open-issues::``
   Each requirement that isn't green, red first, with the scripts (and
   variations) keeping it so: failed at which step, incomplete, not run or
   outdated. Then each failure once: its run, the step, the message and
   the requirements it fails. Scripts that didn't pass but cover no
   requirement come last.

``.. requirement-results::``
   Each requirement the report tests: its text as the report kept it, its
   verdict, and the scripts covering it, one line each, saying how its
   variations came out when they didn't all pass.

   ``:group-by:``
      ``subsystem`` (the default) or ``none``.
   ``:subsystem:``
      Only this subsystem's requirements.
   ``:color:``
      Only requirements with this verdict: ``green``, ``red``, ``partial``
      or ``untested``.

``.. script-results::``
   Each script once: its verdict (the worst of its variations' latest runs)
   and how many variations it has, with how they came out when not alike.

``.. results::``
   The latest run of each combination, its run, outcome and duration. The
   default template leaves it, ``reruns`` and ``failures`` out; add them for
   a run-by-run log.

   ``:script:``
      Only scripts matching this pattern, e.g. ``LND/*``.
   ``:state:``
      Only combinations in this state, e.g. ``fail``.

``.. reruns::``
   Earlier attempts of each combination, newest first.

``.. failures::``
   For each failing combination: its run, the step it failed at, and the
   message.

``.. report-bundle::``
   What the exported bundle holds, and its manifest's SHA-256.

Values in prose
---------------

``:report:`name``` writes one value:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Name
     - Value
   * - ``title``, ``number``, ``revision``, ``author``
     - The document's fields.
   * - ``id``
     - The report's id.
   * - ``context``
     - The requirements context the report verifies.
   * - ``runs``
     - How many runs it has.
   * - ``requirements``, ``requirements.green`` (any verdict)
     - How many requirements it tests, in all or with that verdict.
   * - ``combinations``, ``combinations.fail`` (any state)
     - How many combinations it covers, in all or in that state.
   * - ``uut.NAME``
     - The version of a UUT the report runs on.
   * - ``first_run``, ``last_run``
     - When its first run started and its last ended.

For example::

   This report verifies the lunar module, Luminary :report:`uut.lm`,
   against :report:`context`: :report:`requirements.green` of its
   :report:`requirements` requirements passed.

Snippets
--------

What a directive writes comes from a snippet: a Jinja template that writes
reStructuredText, named after the directive (``report/results.rst`` for
``.. results::``). In a snippet:

- a line starting ``%`` is a Jinja statement (``% for row in rows``), and one
  starting ``%#`` a comment; either line is dropped whole, so blank lines come
  out as written;
- ``{{ value }}`` writes the value as plain text, never markup;
- filters write markup: ``literal``, ``verdict``, ``link(url)``,
  ``requirement`` (a requirement's text), ``indent(n)``, ``verbatim`` (a
  literal block's body), ``heading(char)``, and ``seconds``, ``plural``,
  ``stamp`` for numbers and times;
- ``data`` is the report (``data.combinations``, ``data.requirements``,
  ``data.runs``, ``data.document``, ...), and ``options`` the directive's
  options.

A snippet is looked up in the report template's ``snippets/`` folder first,
then in plugins', then among the built-in ones (in
``automationv3/documents/snippets/``). To change how a part of every report
reads, copy the built-in snippet into your workspace template's
``snippets/report/`` and edit it.

How outputs differ
------------------

A snippet writes the same reStructuredText for every output: live pages
render it with docutils, a frozen report's site and PDF with Sphinx. What it
wants shown differently carries a class: ``:verdict:`fail``` (bold text in
an inline classed ``verdict-fail``) and ``.. container:: requirement``. Live
pages and the site style them with CSS; the PDF with the LaTeX commands they
become (``\DUroleverdict-fail``, the ``sphinxclassrequirement`` environment),
which the template's ``latex.tex_t`` defines.
