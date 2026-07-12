"""Single Instance Lock — prevents multiple GUI instances.

Uses a local TCP socket as a reliable lock mechanism on Windows.
"""

import socket
import sys
import threading

LOCK_PORT = 19876  # Fixed port for single-instance lock


class SingleInstance:
    """Ensures only one instance of the application runs."""

    def __init__(self):
        self._lock_socket = None
        self._is_first = False

    def try_acquire(self) -> bool:
        """Try to acquire the single-instance lock.

        Returns True if this is the first instance, False if another is running.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(('127.0.0.1', LOCK_PORT))
            sock.listen(1)
            self._lock_socket = sock
            self._is_first = True
            return True
        except OSError:
            sock.close()
            # Port is in use — another instance is running
            self._is_first = False
            return False

    def release(self):
        """Release the lock."""
        if self._lock_socket:
            try:
                self._lock_socket.close()
            except Exception:
                pass
            self._lock_socket = None

    @property
    def is_first(self) -> bool:
        return self._is_first
