"""Who may change a report

On a central server a report has an owner (who made it) and
collaborators the owner adds. They, and admins, may change it: queue into
it, rerun, edit its document, freeze and reopen it. Everyone signed in may
read it. A report made before accounts (no owner) is changed by admins.

`email` None means single-user mode: there is nobody to tell apart, and
anyone may do anything.
"""

from . import store


def members(report):
    """The owner and collaborators, owner first"""
    owner = report.get("owner")
    return ([owner] if owner else []) + list(report.get("collaborators", []))


def is_member(report, email):
    return email is not None and email.lower() in {m.lower() for m in members(report)}


def can_change(report, email, admin=False):
    if email is None or admin:
        return True
    return is_member(report, email)


def add_collaborator(root, report_id, email):
    report = store.load_report(root, report_id)
    email = email.strip().lower()
    if is_member(report, email):
        return report
    return store.update_report(root, report_id,
                               collaborators=[*report.get("collaborators", []), email])


def remove_collaborator(root, report_id, email):
    report = store.load_report(root, report_id)
    kept = [c for c in report.get("collaborators", []) if c.lower() != email.strip().lower()]
    return store.update_report(root, report_id, collaborators=kept)
