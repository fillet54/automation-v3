"""Services: the concepts that need storage or processes

Workspaces, requirements, reports, the job queue and workers. Everything
here works without Flask, so it can be driven from the web app, the
command line or tests alike. The web layer (automationv3.web) only
adapts these to HTTP.
"""
