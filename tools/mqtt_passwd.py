"""Generuje wpisy pliku haseł Mosquitto (PBKDF2-SHA512, format $7$).

Użycie:
    python tools/mqtt_passwd.py -c mosquitto/config/passwd esp32_user iot-dev-pass
    python tools/mqtt_passwd.py mosquitto/config/passwd rpi_gateway iot-dev-pass
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
from pathlib import Path


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str, *, iterations: int = 101) -> str:
    salt = secrets.token_bytes(12)
    digest = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=64,
    )
    return f"$7${iterations}${_b64(salt)}${_b64(digest)}"


def main() -> None:
    p = argparse.ArgumentParser(description="Generator pliku passwd dla Mosquitto.")
    p.add_argument("passwd_file", type=Path)
    p.add_argument("username")
    p.add_argument("password")
    p.add_argument("-c", "--create", action="store_true", help="Utwórz nowy plik (nadpisz)")
    args = p.parse_args()

    line = f"{args.username}:{hash_password(args.password)}\n"
    mode = "w" if args.create or not args.passwd_file.exists() else "a"
    args.passwd_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.passwd_file.open(mode, encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except PermissionError:
        raise SystemExit(
            f"Brak uprawnień zapisu: {args.passwd_file}\n"
            f"  sudo chown \"$USER:$USER\" {args.passwd_file}"
        ) from None
    print(f"OK: {args.username} -> {args.passwd_file}")


if __name__ == "__main__":
    main()
