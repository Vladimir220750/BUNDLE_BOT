#!/usr/bin/env python3
# create_token_constants.py
import asyncio
import base64
import json
import random
import sys
import time
from typing import Any, Dict

import httpx

# =======================
# 🔧 НАСТРОЙКИ (КОНСТАНТЫ)
# =======================
BASE_URL = "https://revshare.dev"           # например: "http://localhost" или "https://example.com"
MINT_ADDRESS = "HNRMkRydZZrga7CzvhYqg4SwgYGcXRSd19aMrtcL6REV"           # mint адрес токена
MODE = 3                                 # как в твоём JS: если 3 — будет конвертирован в 4
DEV_WALLET = "7MwJoZ2jfH5btNMXwvWMhvBeAAW8PL2JWPLmmMdsXpnS"
DISTRIBUTION_WALLET = ""                 # если пусто: возьмёт DEV_WALLET или MINT_ADDRESS
PRIVATE_KEY = ""                         # приватный ключ дистрибуции (НЕшифрованный, зашифруем ниже); при MODE==3 игнорируется
ENCRYPTION_PASSWORD = "revshare-secure-2023"

WEBSITE = ""
TAX = 10.0                                # Token-2022 transfer fee (если используешь)
BURN_PERCENTAGE = 0.0
COLOR = "#3b82f6"
REWARD_CA = ""                           # при MODE==3 принудительно будет SOL
DEV_FEE_PERCENTAGE = 10.0                # при MODE==3 будет 30
DISTRIBUTION_INTERVAL = 60               # при MODE==3 будет 60
TELEGRAM_CHANNEL_ID = ""                 # если пусто — сгенерируем как в JS

TIMEOUT = 15.0                           # таймаут HTTP, секунд
VERBOSE = True                           # печатать payload (с замаскированным ключом) в stderr

def encrypt_private_key(private_key: str, password: str = ENCRYPTION_PASSWORD) -> str:
    """
    reverse(private_key) -> сдвиг каждого символа на (sum(ord(password)) % 7) -> base64
    Это НЕ криптостойкая схема — просто совместимость с исходным JS.
    """
    if private_key is None:
        raise ValueError("private_key обязателен для шифрования")
    shift = sum(ord(ch) for ch in password) % 7
    r = "".join(chr(ord(ch) + shift) for ch in private_key[::-1])
    return base64.b64encode(r.encode("utf-8")).decode("ascii")

def build_payload() -> Dict[str, Any]:
    channel_id = TELEGRAM_CHANNEL_ID.strip() if TELEGRAM_CHANNEL_ID else ""
    if not channel_id:
        channel_id = f"-100{int(time.time())}{random.randint(0, 999)}"

    encrypted_pk = ""
    if MODE != 3 and PRIVATE_KEY:
        encrypted_pk = encrypt_private_key(PRIVATE_KEY, ENCRYPTION_PASSWORD)

    dev_wallet_for_mode3 = DEV_WALLET or "7MwJoZ2jfH5btNMXwvWMhvBeAAW8PL2JWPLmmMdsXpnS"
    distribution_wallet_for_mode3 = DISTRIBUTION_WALLET or MINT_ADDRESS or DEV_WALLET

    payload = {
        "mint_address": MINT_ADDRESS,
        "dev_wallet": dev_wallet_for_mode3 if MODE == 3 else (DEV_WALLET or ""),
        "telegram_bot": "n/a",
        "telegram_channel_id": "-100123456789" if MODE == 3 else channel_id,
        "min_holding": 100000,
        "dev_fee_percentage": 30 if MODE == 3 else DEV_FEE_PERCENTAGE,
        "distribution_interval": 60 if MODE == 3 else DISTRIBUTION_INTERVAL,
        "distribution_wallet": (
            distribution_wallet_for_mode3 if MODE == 3 else (DISTRIBUTION_WALLET or DEV_WALLET or MINT_ADDRESS)
        ),
        "distribution_private_key": (
            "placeholder-not-used-for-mode-3" if MODE == 3 else (encrypted_pk or "")
        ),
        "website": WEBSITE or "",
        "tax": 0 if TAX is None else TAX,
        "burn_percentage": 0 if MODE == 3 else (BURN_PERCENTAGE or 0),
        "color": COLOR or "#3b82f6",
        "reward_ca": "So11111111111111111111111111111111111111112" if MODE == 3 else (REWARD_CA or ""),
        # Конвертация режима: 3 -> 4
        "mode": 4 if MODE == 3 else (MODE or 0),
        "skip_distribution_funding": True if MODE == 3 else False,
    }
    return payload

async def call_create_token(base_url: str, payload: Dict[str, Any], timeout: float = TIMEOUT) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/api/create-token"
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        body_text = resp.text
        if not resp.is_success:
            raise httpx.HTTPStatusError(
                f"API request failed: HTTP {resp.status_code} {resp.reason_phrase} — {body_text}",
                request=resp.request,
                response=resp,
            )
        try:
            return resp.json()
        except Exception as e:
            raise ValueError(f"Invalid JSON response: {e}; raw body: {body_text[:500]}") from e

async def main():
    payload = build_payload()

    if VERBOSE:
        redacted = dict(payload)
        print(">> Payload:", json.dumps(redacted, ensure_ascii=False, indent=2), file=sys.stderr)

    try:
        resp_json = await call_create_token(BASE_URL, payload)
        print(json.dumps(resp_json, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
