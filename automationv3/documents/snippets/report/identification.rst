%# .. report-identification::  what the report is, what it ran on, and
%# (exported) the bundle the document describes
.. list-table:: Report
   :header-rows: 1
   :widths: 25 75

   * - Item
     - Value
   * - Report
     - {{ data.id | literal }}
   * - Name
     - {{ data.name }}
   * - Workspace
     - {{ data.report.get("workspace") or "-" }}
   * - Created
     - {{ data.report.get("created") | stamp }}
   * - Runs
     - {{ data.runs | length }}, from {{ data.first_run | stamp or "-" }} to {{ data.last_run | stamp or "-" }}
   * - UUT versions
     - {{ data | uut_versions or "-" }}
   * - Environments
     - {{ data | environments or "-" }}
   * - Requirements
     - {{ data.report.get("requirement_context") or "trunk" }}
% if context.exported
   * - Exported
     - {{ context.exported | stamp }}
   * - Bundle
     - {{ ("report-%s.zip" % data.id) | literal }}
   * - Manifest SHA-256
     - {{ context.manifest_hash | literal }}
% endif
