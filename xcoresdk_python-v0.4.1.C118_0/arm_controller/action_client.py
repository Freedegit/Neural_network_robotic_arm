"""Send left / right / stop to the arm, or auto-receive SNN actions.

Modes:
  --action left|right|stop|-1|1|0   send one action
  --interactive                     type actions, keep one arm connection
  --auto                            listen for root/SNN actions and forward them

Wire protocol to the arm:
  left -> -1
  right -> 1
  stop -> 0

The client is fire-and-forget: it writes the line and does not wait for a reply.
In --auto mode the upstream may send either words or numbers:
  --from-snn:  0=left, 1=right, 2=stop
  default:    -1=left, 1=right, 0=stop
"""
import argparse
import os
import socket
import threading

DEFAULT_HOST = os.environ.get("ARM_HOST", "172.30.187.22")
DEFAULT_PORT = int(os.environ.get("ARM_PORT", "9000"))
DEFAULT_LISTEN_HOST = os.environ.get("ARM_LISTEN_HOST", "0.0.0.0")
DEFAULT_LISTEN_PORT = int(os.environ.get("ARM_LISTEN_PORT", "9000"))

ACTION_CODES = {"left": "-1", "right": "1", "stop": "0"}
ACTION_ALIASES = {
    "left": "left", "-1": "left",
    "right": "right", "1": "right",
    "stop": "stop", "0": "stop",
}
SNN_ALIASES = {
    "left": "left", "0": "left",
    "right": "right", "1": "right",
    "stop": "stop", "2": "stop",
}


def normalize_action(value):
    return ACTION_ALIASES.get(str(value).strip().lower())


def normalize_snn_action(value):
    return SNN_ALIASES.get(str(value).strip().lower())


def send_action(action, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5.0):
    canonical = normalize_action(action)
    if canonical is None:
        raise ValueError("invalid action: %s" % action)
    code = ACTION_CODES[canonical]
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall((code + "\n").encode("utf-8"))
    return "sent %s (%s)" % (canonical, code)


def interactive(host, port, timeout=5.0):
    print("connecting to %s:%s" % (host, port), flush=True)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        print("commands: left/-1, right/1, stop/0, q", flush=True)
        while True:
            try:
                text = input("> ").strip().lower()
            except EOFError:
                break
            if text in ("q", "quit", "exit"):
                break
            canonical = normalize_action(text)
            if canonical is None:
                print("invalid; use left/-1, right/1, stop/0", flush=True)
                continue
            sock.sendall((ACTION_CODES[canonical] + "\n").encode("utf-8"))
            print("sent %s (%s)" % (canonical, ACTION_CODES[canonical]), flush=True)


def handle_auto_client(conn, addr, arm_host, arm_port, from_snn, dry_run, send_lock):
    print("auto client connected: %s" % (addr,), flush=True)
    buffer = b""
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                text = raw.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                action = normalize_snn_action(text) if from_snn else normalize_action(text)
                if action is None:
                    print("auto invalid action: %r" % text, flush=True)
                    continue
                if dry_run:
                    print("auto dry-run %s (%s)" % (action, ACTION_CODES[action]), flush=True)
                else:
                    try:
                        with send_lock:
                            print("auto " + send_action(action, arm_host, arm_port), flush=True)
                    except OSError as exc:
                        print("auto send failed: %s" % exc, flush=True)
    except ConnectionResetError:
        pass
    finally:
        conn.close()
        print("auto client disconnected: %s" % (addr,), flush=True)


def serve_auto(listen_host, listen_port, arm_host, arm_port, from_snn, dry_run):
    send_lock = threading.Lock()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((listen_host, listen_port))
        server.listen()
        print(
            "auto listening on %s:%s -> arm %s:%s (from_snn=%s dry_run=%s)"
            % (listen_host, listen_port, arm_host, arm_port, from_snn, dry_run),
            flush=True,
        )
        while True:
            conn, addr = server.accept()
            threading.Thread(
                target=handle_auto_client,
                args=(conn, addr, arm_host, arm_port, from_snn, dry_run, send_lock),
                daemon=True,
            ).start()


def main():
    parser = argparse.ArgumentParser(description="ROKAE arm action client")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--action", help="left/-1, right/1, stop/0")
    group.add_argument("--interactive", action="store_true")
    group.add_argument("--auto", action="store_true", help="listen for upstream actions")
    parser.add_argument("--host", default=DEFAULT_HOST, help="arm server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="arm server port")
    parser.add_argument("--listen-host", default=DEFAULT_LISTEN_HOST)
    parser.add_argument("--listen-port", type=int, default=DEFAULT_LISTEN_PORT)
    parser.add_argument("--from-snn", action="store_true", help="upstream sends 0=left,1=right,2=stop")
    parser.add_argument("--dry-run", action="store_true", help="auto mode: log without sending")
    args = parser.parse_args()

    if args.auto:
        if args.listen_port == args.port and args.host in ("127.0.0.1", "localhost", "0.0.0.0"):
            parser.error("listen port equals local arm port; use --listen-port 9100")
        try:
            serve_auto(
                args.listen_host,
                args.listen_port,
                args.host,
                args.port,
                args.from_snn,
                args.dry_run,
            )
        except KeyboardInterrupt:
            print("auto stopped", flush=True)
        return

    if args.interactive:
        try:
            interactive(args.host, args.port)
        except OSError as exc:
            print("connection/send failed: %s" % exc, flush=True)
        return

    canonical = normalize_action(args.action)
    if canonical is None:
        parser.error("--action must be left/-1, right/1, stop/0")
    if args.dry_run:
        print("dry-run %s (%s)" % (canonical, ACTION_CODES[canonical]), flush=True)
        return
    try:
        print(send_action(canonical, args.host, args.port), flush=True)
    except OSError as exc:
        print("connection/send failed: %s" % exc, flush=True)


if __name__ == "__main__":
    main()
