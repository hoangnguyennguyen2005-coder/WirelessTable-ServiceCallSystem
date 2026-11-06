"""Real pyserial transport. Parser isolated for testing; no success stub."""

import json
import logging
import threading
import serial
from pydantic import ValidationError
from app.domain.models import DeviceEvent, DomainError

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
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="serial-gateway"
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

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
                    parser = FrameParser()
                    seen_errors = 0
                    while not self.stop_event.is_set():
                        for event in parser.feed(transport.read(1024)):
                            try:
                                self.service.event(event)
                                # COMMIT has returned before bytes are sent.
                                commands = (
                                    self.service.commands(event.node_id)
                                    if event.message_type
                                    in ("CALL", "DONE", "STATUS_POLL")
                                    else []
                                )
                                for command in commands:
                                    try:
                                        transport.write(
                                            (json.dumps(command) + "\n").encode()
                                        )
                                    except (OSError, serial.SerialException) as error:
                                        self.service.transport_error(
                                            command["command_id"], str(error)
                                        )
                                        raise
                            except DomainError as error:
                                response = dict(
                                    protocol_version=1,
                                    message_type="ERROR",
                                    event_id=event.event_id,
                                    node_id=event.node_id,
                                    payload=dict(reason=error.reason),
                                )
                                transport.write((json.dumps(response) + "\n").encode())
                        if parser.errors != seen_errors:
                            self.parser_errors += parser.errors - seen_errors
                            seen_errors = parser.errors
                            log.warning("Rejected serial frames: %s", parser.errors)
            except (OSError, serial.SerialException) as error:
                self.connected, self.error = False, str(error)[:200]
                self.stop_event.wait(delay)
                delay = min(delay * 2, 16)
            except Exception:
                self.connected, self.error = False, "Lỗi gateway; xem server log"
                log.exception("Gateway worker failure")
                self.stop_event.wait(2)
        self.connected = False

    def status(self):
        return dict(
            connected=self.connected,
            error=self.error,
            parser_errors=self.parser_errors,
            port=self.port,
            baud=self.baud,
        )
