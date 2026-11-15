"""The language server on stdin and stdout, as editors start it:
`automation-v3 lsp`

Each message is JSON with a Content-Length header before it.
"""

import json
import sys

from .server import Server


def read_message(stream):
    """The next message on `stream` (binary), or None at its end"""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            if length is None:
                continue
            break
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value)
    body = stream.read(length)
    if len(body) < length:
        return None
    return json.loads(body)


def write_message(stream, message):
    body = json.dumps(message).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    stream.flush()


def serve(root=None, stdin=None, stdout=None, requirements=None):
    """Answer messages until the client says exit, or hangs up. Returns
    the process's exit status."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    server = Server(root, requirements)
    shut_down = False
    while not server.exited:
        message = read_message(stdin)
        if message is None:
            break
        shut_down = shut_down or message.get("method") == "shutdown"
        for reply in server.handle(message):
            write_message(stdout, reply)
    return 0 if shut_down else 1
