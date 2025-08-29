# app/core/wallet_manager.py
from __future__ import annotations

import os
import asyncio
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from spl.token.instructions import (
    get_associated_token_address,
    create_idempotent_associated_token_account,
)
from solana.rpc.types import TxOpts

from .client import SolanaClient
from .constants import SOL_WRAPPED_MINT, TOKEN_PROGRAM_ID, LAMPORTS_PER_SOL

# Загружаем .env один раз (если окружение не подставлено внешним менеджером)
load_dotenv(override=False)

WALLETS_DIR_DEFAULT = os.getenv("WALLETS_DIR", "wallets")
FUND_PRIVATE_KEY_ENV = os.getenv("FUND_PRIVATE_KEY")  # base58 приватник фонда (обязательно!)

@dataclass
class DevWallet:
    keypair: Keypair

class WalletManager:
    """
    Управляет фондом и текущим dev-кошельком.
    - Фонд: грузим приватник из .env (FUND_PRIVATE_KEY).
    - Dev: создаём при инициализации и по требованию update_dev().
    - Любой созданный кош пишем в файл: wallets/{PUBKEY}.txt (base58 приватник в содержимом).
    - Переводы:
        * distribute_lamports(lamports): Фонд → Dev
        * withdraw_to_fund(lamports=None): Dev → Фонд (если None, переводим ВСЁ, за вычетом минимального пыля)
    - Rollover после цикла:
        * rollover_dev(seed_lamports): Dev → Фонд → create new Dev → Фонд → новый Dev (seed_lamports)
    """

    def __init__(self, client: SolanaClient, wallets_dir: str = WALLETS_DIR_DEFAULT):
        if not FUND_PRIVATE_KEY_ENV:
            raise RuntimeError("FUND_PRIVATE_KEY not set in .env")

        self.client = client
        self.wallets_dir = wallets_dir
        os.makedirs(self.wallets_dir, exist_ok=True)

        # Фонд
        self._fund = Keypair.from_base58_string(FUND_PRIVATE_KEY_ENV)
        self._persist_wallet(self._fund)

        # Dev
        self._dev = self._create_dev()

    # ---------- properties ----------
    @property
    def fund(self) -> Keypair:
        return self._fund

    @property
    def fund_pubkey(self) -> Pubkey:
        return self._fund.pubkey()

    @property
    def dev(self) -> Keypair:
        return self._dev.keypair

    @property
    def dev_pubkey(self) -> Pubkey:
        return self._dev.keypair.pubkey()

    # ---------- public API ----------
    async def distribute_lamports(self, lamports: int) -> str:
        """
        Отправить lamports С ФОНДА на ТЕКУЩЕГО DEVA. Возвращает сигнатуру транзакции.
        """
        if lamports <= 0:
            raise ValueError("lamports must be > 0")
        ix = transfer(TransferParams(from_pubkey=self.fund_pubkey,
                                     to_pubkey=self.dev_pubkey,
                                     lamports=lamports))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._fund,
            signers_keypairs=[self._fund],
            label="FUND→DEV",
            priority_fee=0,
        )
        return sig

    async def withdraw_to_fund(self, lamports: Optional[int] = None, *, keep_rent_lamports: int = 0) -> str:
        """
        Отправить lamports с DEVA на ФОНД. Если lamports=None — перевести весь доступный баланс,
        оставив keep_rent_lamports (по умолчанию 0). Возвращает сигнатуру.
        """
        current = await self.client.get_balance_sol(self.dev_pubkey)
        current_lamports = int(current * LAMPORTS_PER_SOL)
        amount = lamports if lamports is not None else max(0, current_lamports - keep_rent_lamports)
        if amount <= 0:
            raise RuntimeError("Nothing to withdraw from dev wallet")

        ix = transfer(TransferParams(from_pubkey=self.dev_pubkey,
                                     to_pubkey=self.fund_pubkey,
                                     lamports=amount))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._dev.keypair,
            signers_keypairs=[self._dev.keypair],
            label="DEV→FUND",
            priority_fee=0,
        )
        return sig

    def update_dev(self) -> Keypair:
        """
        Создать НОВОГО дева, записать файл, вернуть Keypair.
        (Старый dev остаётся «как есть» — его средства нужно слить заранее.)
        """
        self._dev = self._create_dev()
        return self._dev.keypair

    async def rollover_dev(self, seed_lamports: int, *, keep_rent_lamports: int = 0) -> tuple[str, str]:
        """
        Сценарий «после цикла»:
          1) DEV → FUND (всё, либо с оставлением пыли keep_rent_lamports)
          2) создать НОВОГО dev
          3) FUND → NEW_DEV (seed_lamports)
        Возвращает (sig_dev_to_fund, sig_fund_to_new_dev)
        """
        sig1 = await self.withdraw_to_fund(lamports=None, keep_rent_lamports=keep_rent_lamports)
        self.update_dev()
        sig2 = await self.distribute_lamports(seed_lamports)
        return sig1, sig2

    # Хелперы для WSOL ATA — полезно в других частях приложения
    def get_wsol_ata(self, owner: Pubkey) -> Pubkey:
        return get_associated_token_address(owner=owner, mint=SOL_WRAPPED_MINT)

    def build_create_wsol_ata_ix(self, payer: Pubkey):
        return create_idempotent_associated_token_account(payer=payer, owner=payer, mint=SOL_WRAPPED_MINT)

    # ---------- internal ----------
    def _create_dev(self) -> DevWallet:
        kp = Keypair()
        self._persist_wallet(kp)
        return DevWallet(keypair=kp)

    def _persist_wallet(self, kp: Keypair) -> None:
        """
        Записать файл c приватником (base58) в wallets/{PUBKEY}.txt
        """
        # solders.Keypair поддерживает from_base58_string; base58 вывожу через to_bytes → to_base58 (встроенный метод solders чаще есть как to_base58_string()).
        # Если в твоей версии нет .to_base58_string(), раскомментируй ручной b58 encode.
        try:
            secret_b58 = kp.to_base58_string()  # type: ignore[attr-defined]
        except AttributeError:
            # Фолбэк на стандартный формат (как его обычно вводят пользователи — 64 байта secret key в base58)
            import base58  # pip install base58 (если нужно)
            secret_b58 = base58.b58encode(kp.to_bytes()).decode("ascii")

        path = os.path.join(self.wallets_dir, f"{kp.pubkey()}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(secret_b58)
