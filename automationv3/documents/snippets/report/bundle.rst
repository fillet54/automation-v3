%# .. report-bundle::  what the exported bundle holds
This document describes the bundle report-{{ data.id }}.zip. Its folder
report-{{ data.id }} holds the report: ``report.json``, this document's source
``report.rst`` and its ``template/``, and for each run ``run.json``, the exact
files it executed (``closure/``), every event it recorded (``events.jsonl``)
and the files attached to it (``files/``). ``MANIFEST.sha256`` lists a SHA-256
for each of those files{% if context.manifest_hash %}; its own SHA-256 is
{{ context.manifest_hash | literal }}{% endif %}.
