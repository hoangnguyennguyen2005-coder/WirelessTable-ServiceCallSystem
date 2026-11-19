"""Real pyserial transport for the USB radio gateway (ESP32-C3 + nRF24L01+).

The gateway only bridges radio and USB (logbook Step 5 "Bridge radio/USB"): it preserves
endpoint and transaction identity and can never confirm registration or completion itself.
Confirmations are written here only after Service.exchange returned, i.e. after the commit.
The parser is isolated for testing; there is no success stub.
"""

import json
import logging
import threading
import time

import serial
from pydantic import ValidationError

from app.domain.models import DeviceEvent

log = logging.getLogger(__name__)


class FrameParser:
    def __init__(self, limit=4096):
        self.limit, self.buffer, self.discarding = limit, bytearray(), False
        self.errors = 0

    def feed(self, chunk: bytes):
        frames = []
        for byte in chunk:
            if byte == 10:
                if not self.discarding and self.buffer:
                    try:
                        frames.append(
                            DeviceEvent.model_validate_json(bytes(self.buffer))
                        )
                    except (ValidationError, ValueError):
                        self.errors += 1
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                self.buffer.append(byte)
                if len(self.buffer) > self.limit:
                    self.buffer.clear()
                    self.discarding = True
                    self.errors += 1
        return frames


class SerialGateway:
    def __init__(self, service, port, baud=115200, factory=serial.Serial):
        self.service, self.port, self.baud, self.factory = service, port, baud, factory
        self.connected, self.error, self.parser_errors = False, None, 0
        self.frames_in, self.last_frame_at = 0, None
        self.stop_event = threading.Event()
        self.thread = None
        self._recorded = None
        self._malformed_at = float("-inf")

    def start(self):
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="serial-gateway"
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _record(self, up):
        """Put link transitions in the event record; a failure the centre observed (ER-F11)."""
        if self._recorded == up:
            return
        self._recorded = up
        try:
            if up:
                self.service.note("GATEWAY_CONNECTED", f"port={self.port}", "gateway")
            else:
                self.service.note(
                    "FAILURE", f"gateway_disconnected:{self.error}", "gateway"
                )
        except Exception:
            log.exception("Could not record gateway link state")

    def _malformed(self, count):
        self.parser_errors += count
        log.warning("Rejected serial frames: %s", self.parser_errors)
        if time.monotonic() - self._malformed_at >= 30:
            self._malformed_at = time.monotonic()
            try:
                self.service.note(
                    "FAILURE",
                    f"gateway_malformed_frame:total={self.parser_errors}",
                    "gateway",
                )
            except Exception:
                log.exception("Could not record malformed frames")

    def run(self):
        delay = 1
        while not self.stop_event.is_set():
            try:
                if not self.port:
                    raise serial.SerialException("Chưa cấu hình PBL_SERIAL_PORT")
                with self.factory(
                    self.port, self.baud, timeout=0.2, write_timeout=1
                ) as transport:
                    self.connected, self.error, delay = True, None, 1
                    self._record(True)
                    parser = FrameParser()
                    seen_errors = 0
                    while not self.stop_event.is_set():
                        for event in parser.feed(transport.read(1024)):
                            self.frames_in += 1
                            self.last_frame_at = time.time()
                            # exchange() has committed before any byte is written back.
                            for frame in self.service.exchange(event, "gateway"):
                                try:
                                    transport.write((json.dumps(frame) + "\n").encode())
                                except (OSError, serial.SerialException) as error:
                                    if frame.get("command_id"):
                                        self.service.transport_error(
                                            frame["command_id"], str(error)
                                        )
                                    raise
                        if parser.errors != seen_errors:
                            self._malformed(parser.errors - seen_errors)
                            seen_errors = parser.errors
            except (OSError, serial.SerialException) as error:
                self.connected, self.error = False, str(error)[:200]
                self._record(False)
                self.stop_event.wait(delay)
                delay = min(delay * 2, 16)
            except Exception:
                self.connected, self.error = False, "Lỗi gateway; xem server log"
                log.exception("Gateway worker failure")
                self._record(False)
                self.stop_event.wait(2)
        self.connected = False

    def status(self):
        return dict(
            connected=self.connected,
            error=self.error,
            parser_errors=self.parser_errors,
            frames_in=self.frames_in,
            last_frame_at=self.last_frame_at,
            port=self.port,
            baud=self.baud,
        )
