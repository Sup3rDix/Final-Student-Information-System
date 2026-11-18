"""Interactive masked password entry, no third-party packages required.

Displays one '*' for each typed character.  Handles Backspace, Enter and Ctrl+C
while never echoing the actual password.  Windows uses msvcrt; Unix terminals
use the standard library's termios/tty.  Non-TTY input uses getpass, which
preserves safe no-echo behavior where keyboard control is unavailable.
"""

import os
import sys
from getpass import getpass


def read_masked(prompt="Password: ", mask="*"):
    """Read a password, showing * markers on interactive terminal devices."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return getpass(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars = []
    try:
        if os.name == "nt":
            import msvcrt

            def read_key():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()  # Ignore special two-key scan codes.
                    return None
                return key

            def restore():
                pass
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            before = termios.tcgetattr(fd)
            tty.setraw(fd)

            def read_key():
                return sys.stdin.read(1)

            def restore():
                termios.tcsetattr(fd, termios.TCSADRAIN, before)

        try:
            while True:
                key = read_key()
                if key is None:
                    continue
                if key in ("\r", "\n"):
                    break
                if key == "\x03":
                    raise KeyboardInterrupt
                if key == "\x04" and not chars:
                    raise EOFError
                if key in ("\b", "\x7f"):
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif key.isprintable() and key != "\x1b" and len(chars) < 256:
                    chars.append(key)
                    sys.stdout.write(mask)
                    sys.stdout.flush()
        finally:
            restore()
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return "".join(chars)
