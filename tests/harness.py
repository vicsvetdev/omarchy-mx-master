"""Drives the real Helper as a subprocess, through its one behavioural seam.

A test gets: a fake device it writes HID++ frames into, settings on the Helper's
standard input, recording fakes ahead of the real tools on PATH, and the state
the Helper publishes on its standard output. Nothing reaches inside the Helper.
"""

from __future__ import annotations

import sys

# Never leave bytecode in the plugin folder. The shell hot-reloads plugin code
# whenever any file under the plugins directory is saved, so a __pycache__
# written by importing a module from here would restart the Helper mid-suite.
# Set before the imports below, and not left to whoever invoked us.
sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HELPER = os.path.join(ROOT, "bin", "mx-master-helper")

sys.path.insert(0, HERE)
from device import FakeDevice  # noqa: E402


class Helper:
    """One Helper process, its device, and the fakes it called."""

    def __init__(self, settings=None, conflict=False, extra_env=None, args=()):
        self.dir = tempfile.mkdtemp(prefix="mx-master-test.")
        self.device = FakeDevice(os.path.join(self.dir, "hidpp.sock"))
        self.log = os.path.join(self.dir, "fakes.log")
        self.autostart = os.path.join(self.dir, "solaar.desktop")
        with open(self.autostart, "w") as fh:
            fh.write("[Desktop Entry]\nType=Application\nName=Solaar\n"
                     "Exec=solaar --window=hide\nX-GNOME-Autostart-enabled=true\n")
        open(self.log, "w").close()

        env = dict(os.environ)
        env["PATH"] = os.path.join(HERE, "fake") + os.pathsep + env["PATH"]
        env["FAKE_LOG"] = self.log
        self.conflict_marker = os.path.join(self.dir, "conflict")
        env["FAKE_CONFLICT"] = self.conflict_marker
        if conflict:
            open(self.conflict_marker, "w").close()
        env["MX_MASTER_DEVICE"] = self.device.path
        env["MX_MASTER_LOCK"] = os.path.join(self.dir, "helper.lock")
        env["MX_MASTER_AUTOSTART"] = self.autostart
        # Which battery warnings have already been given. Per-test by default,
        # so one suite's edges never leak into another's.
        env["MX_MASTER_STATE"] = os.path.join(self.dir, "warned.json")
        env.update(extra_env or {})
        self.env = env

        self.states = []
        self.stderr = []
        self._lock = threading.Lock()
        self.proc = subprocess.Popen(
            [sys.executable, HELPER, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, bufsize=1,
        )
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        if settings is not None:
            self.settings(settings)

    # ------------------------------------------------------------ plumbing

    def _pump_stdout(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                state = json.loads(line)
            except ValueError:
                continue
            with self._lock:
                self.states.append(state)

    def _pump_stderr(self):
        for line in self.proc.stderr:
            with self._lock:
                self.stderr.append(line.rstrip())

    def _write(self, obj):
        try:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def settings(self, values):
        self._write({"settings": values})

    def command(self, name):
        self._write({"cmd": name})

    def tick(self):
        """Run the verify-and-repair pass now instead of waiting for the timer."""
        self.command("refresh")

    # ------------------------------------------------------------ assertions

    @property
    def state(self):
        with self._lock:
            return dict(self.states[-1]) if self.states else None

    def wait(self, predicate, timeout=5.0, what="state"):
        """Wait for a published state matching `predicate`; returns it or None."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                seen = list(self.states)
            for state in reversed(seen):
                if predicate(state):
                    return state
            time.sleep(0.01)
        return None

    def wait_for(self, **fields):
        return self.wait(lambda s: all(s.get(k) == v for k, v in fields.items()))

    def fakes(self):
        """Every fake invocation, in order, as a list of argv lists."""
        try:
            with open(self.log) as fh:
                return [line.rstrip("\n").split("\t") for line in fh if line.strip()]
        except OSError:
            return []

    def calls(self, tool):
        return [argv[1:] for argv in self.fakes() if argv and argv[0] == tool]

    def wait_for_call(self, tool, count=1, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = self.calls(tool)
            if len(got) >= count:
                return got
            time.sleep(0.01)
        return self.calls(tool)

    def settle(self, seconds=0.35):
        """Give debounced and deferred work time to happen (or not)."""
        time.sleep(seconds)

    def start_conflict(self):
        open(self.conflict_marker, "w").close()

    def end_conflict(self):
        try:
            os.unlink(self.conflict_marker)
        except OSError:
            pass

    # ------------------------------------------------------------- teardown

    def stop(self, keep_dir=False):
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self.device.close()
        if not keep_dir:
            shutil.rmtree(self.dir, ignore_errors=True)


class Suite:
    """The house PASS/FAIL runner, in the shape the sibling plugin uses."""

    def __init__(self, title):
        self.title = title
        self.passed = 0
        self.failed = 0

    def expect(self, name, condition):
        if condition:
            print(f"PASS {name}")
            self.passed += 1
        else:
            print(f"FAIL {name}")
            self.failed += 1

    def report(self):
        print("----")
        print(f"{self.passed} passed, {self.failed} failed")
        return 0 if self.failed == 0 else 1
