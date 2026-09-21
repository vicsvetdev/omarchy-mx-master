"""A fake MX Master 3S behind a fake Logi Bolt receiver, speaking HID++ over a socket.

This is the device half of the Helper's one behavioural seam. The Helper opens
whatever `MX_MASTER_DEVICE` points at; here that is a Unix socket this module
listens on, so a test can write synthetic HID++ frames into the Helper and read
back every frame the Helper wrote to the device.

Nothing here knows what the Helper is for. It answers HID++ the way the real
mouse answered it when the protocol was verified against the hardware — the
feature indices, the battery framing and the DPI list below are what the real
MX Master 3S on a Bolt receiver actually replied.
"""

from __future__ import annotations

import os
import socket
import struct
import threading
import time

SHORT = 0x10
LONG = 0x11
FRAME_LEN = {SHORT: 7, LONG: 20}

DEVICE_INDEX = 0x02
RECEIVER_INDEX = 0xFF

# Feature index -> feature id, as the real device reported them.
FEATURES = {
    0x0000: 0x00,  # ROOT
    0x0001: 0x01,  # FEATURE_SET
    0x0005: 0x03,  # DEVICE_NAME
    0x1D4B: 0x04,  # WIRELESS_DEVICE_STATUS
    0x1004: 0x08,  # UNIFIED_BATTERY
    0x1B04: 0x09,  # REPROG_CONTROLS_V4
    0x2201: 0x0D,  # ADJUSTABLE_DPI
}
FEATURE_VERSION = {0x1B04: 5, 0x2201: 2, 0x1004: 3}
INDEX_TO_FEATURE = {v: k for k, v in FEATURES.items()}

GESTURE_CID = 0x00C3
DEVICE_NAME = b"MX Master 3S"

ERR_UNKNOWN_DEVICE = 0x09  # what the receiver answers for a sleeping device


def frames(buf):
    """Split a byte buffer into whole HID++ frames; returns (frames, remainder)."""
    out = []
    while buf:
        size = FRAME_LEN.get(buf[0])
        if size is None:
            buf = buf[1:]
            continue
        if len(buf) < size:
            break
        out.append(buf[:size])
        buf = buf[size:]
    return out, buf


class FakeDevice:
    """Serves HID++ on a Unix socket and records everything written to it."""

    def __init__(self, path):
        self.path = path
        self.writes = []            # every frame the Helper wrote
        self.online = True          # False models a sleeping or absent mouse
        self.battery = 90
        self.battery_status = 0     # 0 discharging, 1 recharging
        self.dpi = 1000
        self.diversion_flags = 0x00  # Diversion, as setCidReporting has left it
        self.notifications_enabled = False

        self._lock = threading.Lock()
        self._conn = None
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(path)
        self._listener.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------- lifecycle

    def close(self):
        self._stop.set()
        try:
            self._listener.close()
        except OSError:
            pass
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except OSError:
                    pass
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def wait_connected(self, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                if self._conn is not None:
                    return True
            time.sleep(0.01)
        return False

    # ------------------------------------------------- what the test drives

    def send(self, frame):
        """Push a raw frame at the Helper, as the receiver would."""
        with self._lock:
            conn = self._conn
        if conn:
            conn.sendall(bytes(frame).ljust(FRAME_LEN[frame[0]], b"\0"))

    def notify(self, feature_id, address, payload=b""):
        """A HID++ 2.0 notification from the mouse, addressed by feature."""
        index = FEATURES[feature_id]
        self.send(bytes([LONG, DEVICE_INDEX, index, address]) + payload)

    def connect(self):
        """The receiver's device-connection notification: link established."""
        self.online = True
        # 0x41 DJ_PAIRING, Bolt protocol 0x10, flags without the 0x40 no-link bit
        self.send(bytes([SHORT, DEVICE_INDEX, 0x41, 0x10, 0x00, 0x34, 0xB0]))

    def disconnect(self):
        """Link lost — the mouse went to sleep, or walked away."""
        self.online = False
        self.send(bytes([SHORT, DEVICE_INDEX, 0x41, 0x10, 0x40, 0x34, 0xB0]))

    def power_cycle(self):
        """Off and on again. The mouse forgets Diversion and its DPI."""
        self.disconnect()
        with self._lock:
            self.diversion_flags = 0x00
            self.dpi = 1000
        self.connect()

    def press_gesture(self):
        """The Gesture Button goes down, reported as a diverted control."""
        self.notify(0x1B04, 0x00, struct.pack("!HHHH", GESTURE_CID, 0, 0, 0))

    def release_gesture(self):
        self.notify(0x1B04, 0x00, struct.pack("!HHHH", 0, 0, 0, 0))

    def move(self, dx, dy):
        """One raw-XY report, as the mouse sends while a diverted control is held."""
        self.notify(0x1B04, 0x10, struct.pack("!hh", dx, dy))

    def broadcast_battery(self, percent, status=0):
        with self._lock:
            self.battery = percent
            self.battery_status = status
        self.notify(0x1004, 0x00, bytes([percent, self._level_for(percent), status, 0]))

    def dpi_writes(self):
        """Every setSensorDpi the Helper issued, as plain integers."""
        out = []
        for f in self.writes:
            if f[2] == FEATURES[0x2201] and (f[3] >> 4) == 0x3:
                out.append((f[5] << 8) | f[6])
        return out

    def arming_writes(self):
        """Every setCidReporting the Helper issued, as (cid, flag byte)."""
        out = []
        for f in self.writes:
            if f[2] == FEATURES[0x1B04] and (f[3] >> 4) == 0x3:
                out.append(((f[4] << 8) | f[5], f[6]))
        return out

    @staticmethod
    def _level_for(percent):
        if percent > 70:
            return 8
        if percent > 30:
            return 4
        if percent > 10:
            return 2
        return 1

    # -------------------------------------------------------------- serving

    def _serve(self):
        try:
            conn, _ = self._listener.accept()
        except OSError:
            return
        with self._lock:
            self._conn = conn
        buf = b""
        conn.settimeout(0.2)
        while not self._stop.is_set():
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            got, buf = frames(buf)
            for frame in got:
                with self._lock:
                    self.writes.append(frame)
                reply = self._answer(frame)
                if reply is not None:
                    try:
                        conn.sendall(bytes(reply).ljust(FRAME_LEN[reply[0]], b"\0"))
                    except OSError:
                        return

    def _answer(self, frame):
        devidx, third, fourth = frame[1], frame[2], frame[3]

        # HID++ 1.0 register write to the receiver (enable notifications).
        if devidx == RECEIVER_INDEX and third == 0x80:
            self.notifications_enabled = True
            return bytes([SHORT, RECEIVER_INDEX, 0x80, fourth]) + frame[4:7]

        if devidx != DEVICE_INDEX:
            return bytes([SHORT, devidx, 0x8F, third, fourth, ERR_UNKNOWN_DEVICE, 0])

        with self._lock:
            online = self.online
        if not online:
            return bytes([SHORT, devidx, 0x8F, third, fourth, ERR_UNKNOWN_DEVICE, 0])

        feature_index, func, swid = third, fourth >> 4, fourth & 0x0F
        head = bytes([LONG, DEVICE_INDEX, feature_index, (func << 4) | swid])
        params = frame[4:]

        if feature_index == FEATURES[0x0000]:
            if func == 0x0:  # getFeature
                fid = (params[0] << 8) | params[1]
                index = FEATURES.get(fid, 0)
                return head + bytes([index, 0x00, FEATURE_VERSION.get(fid, 0)])
            if func == 0x1:  # ping
                return head + bytes([0x04, 0x05, params[2]])

        if feature_index == FEATURES[0x0005]:
            if func == 0x0:
                return head + bytes([len(DEVICE_NAME)])
            if func == 0x1:
                off = params[0]
                return head + DEVICE_NAME[off:off + 16]

        if feature_index == FEATURES[0x1004] and func == 0x1:  # get_status
            with self._lock:
                return head + bytes([self.battery, self._level_for(self.battery), self.battery_status, 0])

        if feature_index == FEATURES[0x2201]:
            if func == 0x0:  # getSensorCount
                return head + bytes([0x01])
            if func == 0x1:  # getSensorDpiList — 200, then step 50 up to 8000
                if params[2] == 0:
                    return head + bytes([0x00, 0x00, 0xC8, 0xE0, 0x32, 0x1F, 0x40, 0x00, 0x00])
                return head + bytes([0x00, 0x00, 0x00])
            if func == 0x2:  # getSensorDpi
                with self._lock:
                    return head + bytes([0x00]) + struct.pack("!HH", self.dpi, 1000)
            if func == 0x3:  # setSensorDpi
                value = (params[1] << 8) | params[2]
                with self._lock:
                    self.dpi = value
                return head + params[:5]

        if feature_index == FEATURES[0x1B04]:
            if func == 0x0:  # getCount
                return head + bytes([0x08])
            if func == 0x2:  # getCidReporting
                with self._lock:
                    flags = self.diversion_flags
                return head + struct.pack("!HBH", GESTURE_CID, flags, GESTURE_CID)
            if func == 0x3:  # setCidReporting
                cid = (params[0] << 8) | params[1]
                bfield = params[2]
                if cid == GESTURE_CID:
                    with self._lock:
                        for value_bit, valid_bit in ((0x01, 0x02), (0x10, 0x20)):
                            if bfield & valid_bit:
                                if bfield & value_bit:
                                    self.diversion_flags |= value_bit
                                else:
                                    self.diversion_flags &= ~value_bit
                return head + params[:5]

        # Anything we do not model answers like a device that does not support it.
        return bytes([SHORT, DEVICE_INDEX, 0xFF, feature_index, fourth, 0x01, 0])
