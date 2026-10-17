Configuration management
========================

.. rst-class:: lead

   Every run records exactly what produced it, and a rerun either reproduces
   that or says it didn't.

What a run records
------------------

The closure
   The script and every ``core.rst`` and import it loaded, as checked in on
   the workspace's branch (edits not yet committed run only in
   :doc:`scratch`), copied into the run's ``closure/`` folder and hashed.
   Changing any of those files later doesn't change what the run says it
   ran.

The variation
   Its name and the values it bound.

UUT versions
   Each UUT's version id and digest, and whether the worker installed it or
   found it already installed.

The environment fingerprint
   What the environment plugin reports about itself (see
   :doc:`../blocks/uuts-and-environments`), plus the framework's own
   fingerprint: its version, its git commit and whether that checkout has
   uncommitted changes (a ``dev`` install).

Identity
--------

The **identity** of a run is a hash of:

.. mermaid::
   :caption: What a run's identity is made of

   flowchart LR
     closure["Closure hash<br/>the script, its core.rst chain and imports"] --> identity
     variation["Variation values"] --> identity
     uuts["UUT versions and digests"] --> identity
     fingerprint["Fingerprint hash<br/>environment facts, framework version and commit"] --> identity
     identity((Identity)):::accent

Two runs with the same identity ran the same test text, the same way, on the
same software, in an environment that reported the same facts. The run page
shows the identity in its details.

Reruns
------

**Rerun** queues a run again exactly: the same stored closure (not the
workspace as it is now), environment, variation and UUT versions, as a new run
in the same report.

If any live worker's environment has the original fingerprint, the rerun is
**pinned** to such a worker, and gets the same identity.

If none does, the environment has **drifted**. The rerun is refused, and the
page shows, for each live worker, which fingerprint fields differ from the
original. From there you can:

- bring an environment back to the original configuration and rerun; or
- choose **Rerun anyway**, which queues it unpinned and marks the new run
  :status:`not identical`, linked to the run it reran.

.. mermaid::
   :caption: A rerun reproduces the original, or says it can't

   flowchart TB
     rerun([Rerun]) --> match{{"A live worker's environment<br/>has the original fingerprint?"}}
     match -- yes --> pinned["Queued, pinned to such a worker:<br/>the stored closure, variation and versions"]
     pinned --> same[The same identity]:::success
     match -- no --> drifted["Refused: drifted<br/>the page shows which fields differ"]:::warning
     drifted -- "an environment is brought back" --> match
     drifted -- Rerun anyway --> unpinned[Queued unpinned]
     unpinned --> other["not identical,<br/>linked to the run it reran"]:::warning

To test the current text of a script instead, add it to the report again
rather than rerunning.

.. note::

   The framework's git commit is part of the fingerprint, so on a development
   checkout any new commit counts as drift. Whether dev installs should
   ignore the commit is an open question.
