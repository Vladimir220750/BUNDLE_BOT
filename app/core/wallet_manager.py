from __future__ import annotations

import base58

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from spl.token.instructions import get_associated_token_address, create_idempotent_associated_token_account

from .client import SolanaClient
from .constants import SOL_WRAPPED_MINT

load_dotenv(override=False)

WALLETS_DIR_DEFAULT = os.getenv("WALLETS_DIR", "wallets")
FUND_PRIVATE_KEY_ENV = os.getenv("FUND_PRIVATE_KEY")

@dataclass
class DevWallet:
    keypair: Keypair

class WalletManager:
    """
    Управление фондом и dev-кошельком.
    - Фонд: приватник берём из .env (FUND_PRIVATE_KEY)
    - Dev: создаём при инициализации и через update_dev()
    - Любой созданный ключ сохраняем в wallets/{PUBKEY}.txt (внутри — base58 secret)
    - Переводы:
        * distribute_lamports(lamports): Фонд → Dev
        * withdraw_to_fund(lamports=None): Dev → Фонд (если None — весь баланс, можно оставить пыль keep_rent_lamports)
    - После цикла:
        * rollover_dev(seed_lamports): Dev→Fund → create new Dev → Fund→NewDev(seed)
    """
    def __init__(self, client: SolanaClient, wallets_dir: str = WALLETS_DIR_DEFAULT):
        if not FUND_PRIVATE_KEY_ENV:
            raise RuntimeError("FUND_PRIVATE_KEY not set in .env")

        self.client = client
        self.wallets_dir = wallets_dir
        os.makedirs(self.wallets_dir, exist_ok=True)

        self._fund = Keypair.from_base58_string(FUND_PRIVATE_KEY_ENV)
        self._persist_wallet(self._fund)

        self._dev = self._create_dev()

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

    async def distribute_lamports(self, lamports: int) -> str:
        if lamports <= 0:
            raise ValueError("lamports must be > 0")
        ix = transfer(TransferParams(from_pubkey=self.fund_pubkey, to_pubkey=self.dev_pubkey, lamports=lamports))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._fund,
            signers_keypairs=[self._fund],
            max_retries=1,
            max_confirm_retries=10,
            label="FUND→DEV",
            priority_fee=10_000,
        )
        return str(sig)

    async def withdraw_to_fund(self, lamports: Optional[int] = None) -> str:
        lamports_balance = (await self.client.get_multiple_accounts_lamports_balances([self.dev_pubkey]))[0]
        amount = lamports if lamports is not None else max(0, lamports_balance)
        if amount <= 0:
            raise RuntimeError("Nothing to withdraw from dev wallet")

        ix = transfer(TransferParams(from_pubkey=self.dev_pubkey, to_pubkey=self.fund_pubkey, lamports=amount))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._dev.keypair,
            signers_keypairs=[self._dev.keypair],
            max_retries=1,
            max_confirm_retries=10,
            label="DEV→FUND",
            priority_fee=10_000,
        )
        return str(sig)

    def update_dev(self) -> Keypair:
        self._dev = self._create_dev()
        return self._dev.keypair

    async def rollover_dev(self, seed_lamports: int) -> tuple[str, str]:
        sig1 = await self.withdraw_to_fund(lamports=None)
        self.update_dev()
        sig2 = await self.distribute_lamports(seed_lamports)
        return sig1, sig2

    @staticmethod
    def get_wsol_ata(owner: Pubkey) -> Pubkey:
        return get_associated_token_address(owner=owner, mint=SOL_WRAPPED_MINT)

    @staticmethod
    def build_create_wsol_ata_ix(payer: Pubkey):
        return create_idempotent_associated_token_account(payer=payer, owner=payer, mint=SOL_WRAPPED_MINT)

    def _create_dev(self) -> DevWallet:
        kp = Keypair()
        self._persist_wallet(kp)
        return DevWallet(keypair=kp)

    def _persist_wallet(self, kp: Keypair) -> None:
        try:
            secret_b58 = base58.b58encode(kp.to_bytes()).decode()
        except AttributeError as e:
            raise RuntimeError(e)

        path = os.path.join(self.wallets_dir, f"{kp.pubkey()}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(secret_b58)
