"""Sending sign-in links

By SMTP through the relay in the server's settings; with no relay (a dev
server) the link is written to the log instead, so it can be clicked from
there.
"""

import logging
import smtplib
from email.message import EmailMessage

log = logging.getLogger("automationv3.mail")


def sign_in_message(sender, to, link, minutes, device=None, brand="automation"):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    if device:
        message["Subject"] = f"Approve signing in {device} to {brand}"
        intro = f"Someone (hopefully you) is signing {device} in to {brand} as {to}."
        action = "To approve it, open this link"
    else:
        message["Subject"] = f"Sign in to {brand}"
        intro = f"Someone (hopefully you) asked to sign in to {brand} as {to}."
        action = "To sign in, open this link"
    message.set_content(
        f"{intro}\n\n{action} within {minutes} minutes. It works once.\n\n"
        f"    {link}\n\nIf it wasn't you, ignore this email: nothing happens "
        f"unless the link is used.\n")
    return message


def send_sign_in(smtp, to, link, minutes, device=None, brand="automation"):
    """Email a sign-in link, or log it when there is no SMTP relay.
    Returns True if it was sent by email."""
    if smtp is None:
        what = f"approve {device}" if device else "sign in"
        log.warning("No [smtp] in the settings: link to %s as %s: %s", what, to, link)
        print(f"   Sign-in link for {to} ({what}): {link}", flush=True)
        return False
    message = sign_in_message(smtp.sender, to, link, minutes, device, brand)
    with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
        if smtp.starttls:
            server.starttls()
        if smtp.username:
            server.login(smtp.username, smtp.password)
        server.send_message(message)
    return True
