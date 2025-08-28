#!/usr/bin/env python3
import argparse
import base64
import re
import sys

_BASE58_RE = re.compile(r'^[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]+$')

def encrypt_private_key(private_key: str, password: str) -> str:
    if private_key is None or password is None:
        raise ValueError("private_key и password обязательны")
    s = private_key[::-1]
    shift = sum(ord(ch) for ch in password) % 7
    r = "".join(chr(ord(ch) + shift) for ch in s)
    return base64.b64encode(r.encode("utf-8")).decode("ascii")

def decrypt_private_key(encrypted: str, password: str) -> str:
    if not encrypted:
        raise ValueError("Пустая зашифрованная строка")
    shift = sum(ord(ch) for ch in password) % 7
    try:
        r = base64.b64decode(encrypted.strip().encode("ascii")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Не удалось декодировать base64: {e}")
    o = "".join(chr(ord(ch) - shift) for ch in r)
    original = o[::-1]
    if not _BASE58_RE.match(original):
        raise ValueError("Decryption failed: Invalid base58 characters in result")
    return original

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Простой (НЕ криптостойкий) шифратор приватника по логике из JS.",
        epilog="Примеры:\n"
               "  crypto_cli.py --enc 5Hu8GmYv3abcDEF s3cr3t\n"
               "  crypto_cli.py --dec U0hBRUQ= s3cr3t",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--enc", action="store_true", help="Зашифровать: вход = приватник")
    g.add_argument("--dec", action="store_true", help="Расшифровать: вход = base64-строка")
    p.add_argument("input", help="Строка входа (приватник для --enc, base64 для --dec)")
    p.add_argument("password", help="Пароль/фраза (ключ)")
    return p.parse_args()

def main():
    args = parse_args()
    try:
        if args.enc:
            out = encrypt_private_key(args.input, args.password)
        else:
            out = decrypt_private_key(args.input, args.password)
        print(out)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
