#!/usr/bin/env python3
# ==============================================================================
# OpenOptOut — Local Mock SIP2 Server for Library ILS Testing
# ==============================================================================
"""Mock SIP2 (3M Standard Interchange Protocol) server for testing library card logins."""
import argparse
import socket
import ssl
import sys
import threading
import time

TEST_PATRONS = {
    "21234000123": {
        "pin": "1234",
        "name": "DOE, JANE",
        "email": "jane.doe@example.org",
        "phone": "555-0100",
        "address": "123 Main St, Springfield",
        "birthdate": "19900101",
        "ptype": "ADULT",
        "home_lib": "MAIN",
        "status": "OK",
    },
    "21234000124": {
        "pin": "1234",
        "name": "SMITH, JOHN",
        "email": "john.smith@example.org",
        "phone": "555-0101",
        "address": "456 Oak Ave, Springfield",
        "birthdate": "19850515",
        "ptype": "EXPIRED",
        "home_lib": "BRANCH1",
        "status": "EXPIRED",
    },
    "21234000125": {
        "pin": "1234",
        "name": "DOE, TOMMY",
        "email": "tommy.doe@example.org",
        "phone": "555-0100",
        "address": "123 Main St, Springfield",
        "birthdate": "20150601",
        "ptype": "JUVENILE",
        "home_lib": "MAIN",
        "status": "OK",
    },
}


def sip2_checksum(msg: str) -> str:
    total = sum(ord(c) for c in msg)
    check = (-total) & 0xFFFF
    return f"{check:04X}"


def handle_client(conn, addr, verbose=True):
    if verbose:
        print(f"[*] Connection received from {addr[0]}:{addr[1]}")
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\r" in buf:
                line, buf = buf.split(b"\r", 1)
                msg = line.decode("ascii", "replace").strip()
                if not msg:
                    continue
                if verbose:
                    print(f"  --> Incoming SIP2: {msg[:100]}")

                # Handle Message 93: Terminal Login
                if msg.startswith("93"):
                    resp_body = "941"  # 94 = Login response, 1 = ok
                    chk = sip2_checksum(resp_body + "AZ")
                    resp = f"{resp_body}AZ{chk}\r"
                    conn.sendall(resp.encode("ascii"))
                    if verbose:
                        print("  <-- Outgoing SIP2: 941 (Login OK)")

                # Handle Message 63: Patron Information Request
                elif msg.startswith("63"):
                    fields = {}
                    # Parse pipe-delimited fields (starts after message header)
                    for item in msg[35:].split("|"):
                        if len(item) >= 2:
                            fields[item[:2]] = item[2:]
                    bc = fields.get("AA", "").strip()
                    pin = fields.get("AD", "").strip()

                    patron = TEST_PATRONS.get(bc)
                    known = patron is not None
                    good_pin = known and patron["pin"] == pin

                    # Message 64 fixed-width prefix
                    now_str = time.strftime("%Y%m%d    %H%M%S")
                    fixed = "64" + " " * 14 + "000" + now_str + "0000" * 6

                    bl = "Y" if known and patron["status"] == "OK" else "N"
                    cq = "Y" if good_pin else "N"
                    ae = patron["name"] if known else ""
                    be = patron["email"] if known else ""
                    bd = patron["birthdate"] if known else ""
                    bf = patron.get("phone", "") if known else ""
                    addr = patron.get("address", "") if known else ""
                    aq = patron["home_lib"] if known else "MAIN"

                    resp_body = (
                        f"{fixed}AOOpenOptOut Library|AA{bc}|AE{ae}|"
                        f"BL{bl}|CQ{cq}|BE{be}|BF{bf}|BD{addr}|AQ{aq}|AY1"
                    )
                    chk = sip2_checksum(resp_body + "AZ")
                    resp = f"{resp_body}AZ{chk}\r"
                    conn.sendall(resp.encode("ascii"))
                    if verbose:
                        print(f"  <-- Outgoing SIP2: 64 Patron Response (Valid: {bl}, PIN OK: {cq})")

                # Handle Message 17: SC Status Request
                elif msg.startswith("17"):
                    now_str = time.strftime("%Y%m%d    %H%M%S")
                    resp_body = f"98YYYYNN600003{now_str}2.00AOMAIN|AMOpenOptOut Test ILS|AY1"
                    chk = sip2_checksum(resp_body + "AZ")
                    resp = f"{resp_body}AZ{chk}\r"
                    conn.sendall(resp.encode("ascii"))
                    if verbose:
                        print("  <-- Outgoing SIP2: 98 Status Response (Online)")
    except Exception as e:
        if verbose:
            print(f"[!] Socket error with {addr}: {e}")
    finally:
        conn.close()
        if verbose:
            print(f"[*] Connection closed for {addr[0]}:{addr[1]}")


def run_server(host="0.0.0.0", port=6001, use_tls=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(16)

    protocol = "SIP2 over TLS" if use_tls else "Plain SIP2 (TCP)"
    print("\n=================================================================")
    print("  OpenOptOut Mock SIP2 Library ILS Server")
    print("=================================================================")
    print(f"Listening on:    {host}:{port} ({protocol})")
    print("Test Patrons:")
    for bc, p in TEST_PATRONS.items():
        print(f"  • Barcode: {bc} | PIN: {p['pin']} | Name: {p['name']} ({p['ptype']})")
    print("-----------------------------------------------------------------")
    print("Configure OpenOptOut to test:")
    print(f"  Host: {host if host != '0.0.0.0' else '127.0.0.1'} (or host.docker.internal from Docker)")
    print(f"  Port: {port}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            conn, addr = sock.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[*] Stopping Mock SIP2 server...")
    finally:
        sock.close()


def run_self_test(host="127.0.0.1", port=6001):
    print(f"[*] Running self-test against {host}:{port}...")
    try:
        s = socket.create_connection((host, port), timeout=5)
    except Exception as e:
        print(f"[✗] Could not connect to {host}:{port}: {e}")
        return 1

    # Send Status Request (17)
    s.sendall(b"1700120260101    120000AY1AZ0000\r")
    resp = s.recv(4096).decode("ascii", "replace")
    if resp.startswith("98"):
        print("  [✓] Status Request (17) -> Response (98) OK")
    else:
        print(f"  [✗] Unexpected status response: {resp}")
        return 1

    # Send Patron Request (63)
    now_str = time.strftime("%Y%m%d    %H%M%S")
    msg = f"63001{now_str}          AOMAIN|AA21234000123|AD1234|AY1"
    chk = sip2_checksum(msg + "AZ")
    s.sendall(f"{msg}AZ{chk}\r".encode("ascii"))
    resp = s.recv(4096).decode("ascii", "replace")
    if resp.startswith("64") and "CQY" in resp and "BLY" in resp:
        print("  [✓] Patron Request (63) -> Response (64) OK (Patron Verified: DOE, JANE)")
    else:
        print(f"  [✗] Patron response check failed: {resp}")
        return 1

    s.close()
    print("[✓] Self-test completed successfully!\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description="OpenOptOut Mock SIP2 ILS Server")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=6001, help="Listen port (default: 6001)")
    parser.add_argument("--test", action="store_true", help="Run self-test client against running server")
    args = parser.parse_args()

    if args.test:
        target_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
        sys.exit(run_self_test(target_host, args.port))
    else:
        run_server(args.host, args.port)


if __name__ == "__main__":
    main()
