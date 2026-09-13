import importlib.util
import json
import sys
import threading
import types
import unittest
import unittest.mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/hermes/iris_client.py"
SPEC = importlib.util.spec_from_file_location("iris_client", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FakeSocket:
    """One shared script across reconnects, so a retry cannot replay the same failure."""

    def __init__(self, script):
        self.script = script

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def recv(self, timeout=None):
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class WatchLoopTests(unittest.TestCase):
    """A quiet room used to tear the socket down every 40s, losing 5s out of every 45."""

    def setUp(self):
        self.frame = json.dumps({
            "sender": "조창희",
            "json": {"id": "9", "chat_id": "7", "user_id": "11", "type": "1",
                     "message": "m", "attachment": "{}", "created_at": "1"},
        })

    def run_loop(self, script):
        connects = []
        stop = threading.Event()
        rows = []

        remaining = list(script)

        def connect(url, open_timeout=None):
            connects.append(url)
            return FakeSocket(remaining)

        client = types.ModuleType("websockets.sync.client")
        client.connect = connect
        sync = types.ModuleType("websockets.sync")
        sync.client = client
        root = types.ModuleType("websockets")
        root.sync = sync
        saved = {name: sys.modules.get(name) for name in
                 ("websockets", "websockets.sync", "websockets.sync.client")}
        sys.modules.update({"websockets": root, "websockets.sync": sync,
                            "websockets.sync.client": client})
        try:
            module.IrisClient("http://x:3000")._watch_loop(
                lambda row: (rows.append(row), stop.set()), {}, stop
            )
        finally:
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        return connects, rows

    def test_idle_timeouts_keep_the_same_connection(self):
        connects, rows = self.run_loop(
            [TimeoutError("timed out in 30.0s"), TimeoutError("timed out in 30.0s"), self.frame]
        )
        self.assertEqual(len(connects), 1)
        self.assertEqual([row["log_id"] for row in rows], [9])

    def test_a_real_drop_still_reconnects(self):
        with unittest.mock.patch.object(module.time, "sleep"):
            connects, rows = self.run_loop([OSError("connection reset"), self.frame])
        self.assertEqual(len(connects), 2)
        self.assertEqual([row["log_id"] for row in rows], [9])


if __name__ == "__main__":
    unittest.main()
