"""The language server for scripts

- service.py: what a server answers from, knowing nothing of the
  protocol: the problems in the open documents and the names that
  complete at a place in one;
- server.py: the Language Server Protocol over those, as messages in and
  messages out, with no transport;
- stdio.py: the server on stdin and stdout (`automation-v3 lsp`), for
  editors.

The web app's editor talks to the same server in cards, through
web/editor.py (PageSession), which builds the text from them.
"""
