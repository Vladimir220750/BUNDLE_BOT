# check_balances.py
from __future__ import annotations
import os
import json
import asyncio
from typing import List, Tuple, Optional, Dict

import httpx
import base58
from solders.keypair import Keypair

# --- НАСТРОЙКИ ---
RPC_URL = os.getenv("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2")
COMBINED_FILE = "all_keys.txt"
CHUNK_SIZE = 100
TIMEOUT = 20.0

# --- УТИЛИТЫ ---
def _parse_secret_to_bytes(s: str) -> bytes:
    """
    Поддерживает 3 формата:
    1) JSON-массив байт: [12,34,...] длиной 64
    2) base58-строка (обычно 88- или 89-символов)
    3) hex-строка без 0x префикса
    """
    s = s.strip().strip(",")
    if not s:
        raise ValueError("empty secret")

    # json array
    if s.startswith("[") and s.endswith("]"):
        arr = json.loads(s)
        return bytes(arr)

    # hex
    if all(c in "0123456789abcdefABCDEF" for c in s) and len(s) in (64, 128):
        return bytes.fromhex(s)

    # base58
    try:
        return base58.b58decode(s)
    except Exception as e:
        raise ValueError(f"cannot decode secret (expected json array / base58 / hex): {e}")

def _load_secrets_from_combined(file_path: str) -> List[str]:
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.read().strip()
    if not data:
        return []
    # поддержим и запятые, и переводы строк
    raw = []
    for piece in data.replace("\n", ",").split(","):
        piece = piece.strip()
        if piece:
            raw.append(piece)
    return raw

def _load_secrets_from_dir(dir_path: str) -> List[str]:
    items: List[str] = []
    for fname in os.listdir(dir_path):
        fpath = os.path.join(dir_path, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                items.append(s)
    return items

def secrets_to_keypairs(secrets: List[str]) -> List[Tuple[str, Keypair]]:
    """
    Возвращает список (исходная_строка, Keypair).
    Пропускает некорректные секреты.
    """
    res: List[Tuple[str, Keypair]] = []
    for s in secrets:
        try:
            sk_bytes = _parse_secret_to_bytes(s)
            # Solders ожидает 64 байта (секретный ключ), иногда дают 32 — обработаем это.
            if len(sk_bytes) == 32:
                # Это "seed" не подходит для непосредственного Keypair.from_bytes
                # Здесь можно бросить ошибку или расширить до 64, если у вас есть публичный ключ.
                # Оставим как ошибка, чтобы не получить некорректную пару.
                raise ValueError("32-byte seed is not a full secret key (need 64 bytes).")
            kp = Keypair.from_bytes(sk_bytes)
            res.append((s, kp))
        except Exception as e:
            print(f"[WARN] Skip secret: {str(e)}")
    return res

async def fetch_balances(pubkeys: List[str]) -> Dict[str, int]:
    balances: Dict[str, int] = {}
    if not pubkeys:
        return balances

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Чанкуем запросы через getMultipleAccounts
        for i in range(0, len(pubkeys), CHUNK_SIZE):
            chunk = pubkeys[i:i+CHUNK_SIZE]
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getMultipleAccounts",
                "params": [chunk, {"encoding": "jsonParsed", "commitment": "processed"}],
            }
            try:
                r = await client.post(RPC_URL, json=payload)
                r.raise_for_status()
                data = r.json()
                # Ответ: result -> value: [ { lamports, ... } or None ]
                value = (data.get("result") or {}).get("value") or []
                for pk, acc in zip(chunk, value):
                    lamports = 0
                    if acc and "lamports" in acc:
                        lamports = acc["lamports"]
                    balances[pk] = lamports
            except Exception as e:
                print(f"[ERR] RPC chunk [{i}:{i+CHUNK_SIZE}] failed: {e}")
                # Заполним нулями, чтобы структура была полной
                for pk in chunk:
                    balances.setdefault(pk, 0)
    return balances

def format_sol(lamports: int) -> str:
    return f"{lamports/1_000_000_000:.9f}"

async def main():
    secrets: List[str] = []
    if COMBINED_FILE and os.path.exists(COMBINED_FILE):
        secrets = _load_secrets_from_combined(COMBINED_FILE)

    if not secrets:
        print("Нет приватников. Укажи COMBINED_FILE или INPUT_DIR.")
        return

    # 2) Превращаем в Keypair и публичные ключи
    pairs = secrets_to_keypairs(secrets)
    if not pairs:
        print("Ни один приватник не удалось распарсить.")
        return

    pubkeys = [str(kp.pubkey()) for _, kp in pairs]

    # 3) Тянем балансы
    balances = await fetch_balances(pubkeys)

    # 4) Печатаем табличку (pubkey, lamports, SOL)
    print(f"Всего кошельков: {len(pubkeys)}   |   RPC: {RPC_URL}")
    print("-" * 80)
    print(f"{'PUBKEY':<44}  {'LAMPORTS':>15}  {'SOL':>15}")
    print("-" * 80)
    nonzero = 0
    for pk in pubkeys:
        lam = int(balances.get(pk, 0))
        if lam > 0:
            nonzero += 1
        print(f"{pk:<44}  {lam:>15}  {format_sol(lam):>15}")
    print("-" * 80)
    print(f"С ненулевым балансом: {nonzero}/{len(pubkeys)}")

if __name__ == "__main__":
    asyncio.run(main())
