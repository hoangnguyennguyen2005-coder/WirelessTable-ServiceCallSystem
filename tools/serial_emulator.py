"""Software gateway emulator: PTY on Linux or an existing virtual serial pair.
Interactive: call N, poll N, done N, duplicate, bad, oversized, fragment N, quit.
Always labelled emulated; no firmware/hardware compatibility claim.
"""
import argparse
import errno
import json
import os
import select
import sys
import time
from uuid import uuid4
import serial

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pty', action='store_true', help='Linux: print slave path for PC adapter')
parser.add_argument('--port', help='Other endpoint of virtual COM pair')
parser.add_argument('--baud', type=int, default=115200)
parser.add_argument('--no-apply', action='store_true', help='Do not send STATUS_APPLIED')
args = parser.parse_args()
if args.pty:
    import pty
    import tty
    master, slave = pty.openpty()
    tty.setraw(slave)
    print(f'EMULATED GATEWAY PC PORT: {os.ttyname(slave)}', flush=True)
    fd = master
    def write(data):
        os.write(master, data)
    def read():
        try:
            return os.read(master, 4096)
        except OSError as error:
            if error.errno == errno.EIO:
                return b''
            raise
elif args.port:
    transport = serial.Serial(args.port, args.baud, timeout=0)
    fd = transport.fileno()
    write, read = transport.write, lambda: transport.read(4096)
else:
    parser.error('Use --pty (Linux) or --port COMx (virtual pair)')

boot = int(uuid4().hex[:8], 16)
nodes, buffer, previous = {}, bytearray(), b''
stdin_buffer, commands = b'', []


def node(number):
    return nodes.setdefault(number, dict(token=0, request_id=None, active=False, pending=None, next_at=0))


def send(kind, number, payload=None, fragment=False):
    global previous
    n = node(number)
    data = dict(protocol_version=1, message_type=kind, event_id=str(uuid4()), node_id=number, boot_id=boot,
                call_token=n['token'], request_id=n['request_id'], payload=payload or {})
    previous = (json.dumps(data) + '\n').encode()
    if fragment:
        write(previous[:17])
        time.sleep(0.05)
        write(previous[17:])
    else:
        write(previous)
    print('EMULATED →', kind, number, flush=True)


print('Serial emulator ready. Commands: call 1 | done 1 | poll 1 | duplicate | bad | oversized | fragment 1 | quit', flush=True)
try:
    while True:
        # stdin select is Linux PTY mode; on Windows use --port with a terminal supporting select or Linux emulator.
        readers = [fd] + ([sys.stdin] if os.name != 'nt' else [])
        ready, _, _ = select.select(readers, [], [], 0.1)
        if sys.stdin in ready:
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                break
            stdin_buffer += chunk
            while b'\n' in stdin_buffer:
                line, _, stdin_buffer = stdin_buffer.partition(b'\n')
                commands.append(line.decode())
        if commands:
            parts = commands.pop(0).strip().split()
            if not parts or parts[0] == 'quit':
                break
            action = parts[0]
            number = int(parts[1]) if len(parts) > 1 else 1
            n = node(number)
            if action in ('call', 'fragment'):
                if not n['active']:
                    n.update(token=n['token'] + 1, request_id=None, active=True, pending='CALL')
                send('CALL', number, fragment=action == 'fragment')
            elif action == 'done':
                n['pending'] = 'DONE'
                send('DONE', number)
            elif action == 'poll':
                send('STATUS_POLL', number)
            elif action == 'duplicate' and previous:
                write(previous)
            elif action == 'bad':
                write(b'not-json\n')
            elif action == 'oversized':
                write(b'x' * 5000 + b'\n')
            n['next_at'] = time.monotonic() + 5
        if fd in ready:
            buffer.extend(read())
            if len(buffer) > 16384:
                buffer.clear()
                print('EMULATED: response buffer overflow', flush=True)
            while b'\n' in buffer:
                line, _, remainder = buffer.partition(b'\n')
                buffer = bytearray(remainder)
                try:
                    command = json.loads(line)
                    print('PC →', json.dumps(command), flush=True)
                    if command['message_type'] == 'ERROR':
                        continue
                    number = command['node_id']
                    n = node(number)
                    if command['boot_id'] != boot or command['call_token'] != n['token']:
                        continue
                    n['request_id'] = command['request_id']
                    if command['message_type'] == 'DONE_RECEIPT' or command['payload']['led'] == 'OFF':
                        n.update(active=False, pending=None)
                    elif command['message_type'] == 'CALL_RECEIPT':
                        n['pending'] = None
                    if not args.no_apply:
                        send('STATUS_APPLIED', number, command['payload'])
                except (ValueError, KeyError, TypeError) as error:
                    print('EMULATED malformed PC response:', str(error), flush=True)
        for number, n in nodes.items():
            if n['active'] and time.monotonic() >= n['next_at']:
                send(n['pending'] or 'STATUS_POLL', number)
                n['next_at'] = time.monotonic() + 5
except KeyboardInterrupt:
    pass
finally:
    if args.pty:
        os.close(master)
        os.close(slave)
    else:
        transport.close()
