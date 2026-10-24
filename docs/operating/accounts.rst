Accounts and sign-in
====================

.. rst-class:: lead

   A central server knows who is asking. There are no passwords: you sign in
   with a link sent to your work email.

Single-user and central
-----------------------

A server started without settings, or with settings that have no ``[auth]``
table, is **single-user**: there's no sign-in and whoever opens it can do
everything, as on a laptop or in the demo.

A server with ``[auth]`` in its settings (``server --settings server.toml``)
is **central**: every page and API call needs a signed-in user, and things
people make (reports, scratch runs) are theirs.

.. code-block:: toml

   base_url = "https://automation.example.com"   # the address in emailed links

   [auth]
   allowed_domains = ["example.com"]   # who may sign in
   admins = ["lead@example.com"]       # who may administer
   session_days = 30                   # default; renewed while used
   link_minutes = 15                   # default; how long a link works

   [smtp]                              # without it, links are printed to the log
   host = "mail.example.com"
   port = 25
   starttls = false
   sender = "automation@example.com"
   # username and password, if the relay needs them; the password can come
   # from AUTOMATION_SMTP_PASSWORD instead

Signing in
----------

#. Open any page. You're asked for your email address.
#. Anyone with an address at one of the ``allowed_domains`` gets a sign-in
   link by email. Their account is made the first time they sign in, with
   no admin needed.
#. The link works **once**, for ``link_minutes``. Opening it shows a
   **Sign in** button rather than signing you in straight away, so mail
   scanners that open links don't use them up.
#. You stay signed in for ``session_days``, and every visit renews that, so
   someone who uses the server at least monthly never signs in again.
   **Sign out** is on the Account page.

Without ``[smtp]`` (a server being tried out) the link is printed in the
server's log, ready to be copied.

Sessions are cookies that scripts on the page can't read, and that other
sites can't send with a form (``SameSite=Lax``). Set ``base_url`` to an
``https://`` address and the cookie is only ever sent over HTTPS.

Devices
-------

The local client (see :doc:`local-client`) signs in with
``automation-v3 login --server URL``. That emails you a link too; opening it
asks you to **Approve** the device, and the client then keeps a token that
acts as you. Your **Account** page lists your devices, when each last
connected, and lets you remove any of them: its token stops working at
once.

Admins
------

Admins are the addresses in ``admins``. Being listed is checked on every
request, so a change to the settings takes effect when the server restarts,
and the settings' history shows who was an admin when. The **Admin** page
lists everyone who has signed in, and holds the tokens workers use (see
:doc:`workers`).

What is kept
------------

The database keeps each user's email, when they first signed in and when
they were last seen. Links, sessions and tokens are random secrets that are
shown or sent once; only their SHA-256 is stored, so a copy of the database
can't be used to sign in.
