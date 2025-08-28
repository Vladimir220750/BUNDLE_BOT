from __future__ import annotations
import sys, asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import struct
import httpx

import time
import random
from collections import deque
from collections.abc import Callable
from inspect import Signature
from typing import Any
from solana.rpc.commitment import Processed, Commitment
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.solders import SimulateTransactionResp
from solders.transaction import Transaction


import sys
import structlog
from loguru import logger as _log

from typing import Optional
from enum import Enum
from dataclasses import dataclass
import json
import os
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from spl.token.instructions import transfer_checked, get_associated_token_address, TransferCheckedParams, \
    create_idempotent_associated_token_account
from spl.token.constants import TOKEN_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from pathlib import Path
import asyncio

WALLETS_DIR = Path("wallets")

def _setup_logger(level="DEBUG"):
    _log.remove()
    _log.add(sys.stdout,
             level=level.upper(),
             colorize=True,
             enqueue=False,
             format="<green>{time:HH:mm:ss.SSS}</green> "
                    "<level>{level: <8}</level> "
                    "<cyan>{function}</cyan>:<cyan>{line}</cyan> "
                    "- <level>{message}</level>")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level.upper()),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ]
    )
    return structlog.get_logger()
logger = _setup_logger("INFO")

class AsyncRateLimiter:
    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self.calls = deque()

    async def wait(self):
        now = time.monotonic()
        while len(self.calls) >= self.max_calls:
            elapsed = now - self.calls[0]
            if elapsed < self.per_seconds:
                wait_time = self.per_seconds - elapsed
                await asyncio.sleep(min(wait_time, 0.01))
                now = time.monotonic()
            else:
                self.calls.popleft()
        self.calls.append(now)

class ExponentialBackoff:
    def __init__(self, min_delay=0.2, max_delay=5.0, factor=2.0, jitter=0.2):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.factor = factor
        self.jitter = jitter
        self._current = self.min_delay

    async def delay(self):
        jitter = random.uniform(1 - self.jitter, 1 + self.jitter)
        delay = min(self._current * jitter, self.max_delay)
        logger.debug(f"[Backoff] Sleeping for {delay:.2f}s due to rate limit...")
        await asyncio.sleep(delay)
        self._current = min(self._current * self.factor, self.max_delay)

    def reset(self):
        self._current = self.min_delay

class PatchedHttpxClient(httpx.AsyncClient):
    def __init__(self, *args, max_retries: int = 10, limiter: AsyncRateLimiter, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_retries = max_retries
        self._limiter = limiter
        self._backoff = ExponentialBackoff()

    async def send(self, request: httpx.Request, *args, **kwargs) -> httpx.Response:
        for attempt in range(self._max_retries):
            await self._limiter.wait()
            response = await super().send(request, *args, **kwargs)

            if response.status_code != 429:
                return response

            logger.debug(f"[PatchedHttpxClient] 429 Too Many Requests → attempt {attempt+1}/{self._max_retries} for {request.url}")
            await self._backoff.delay()

        logger.info(f"[PatchedHttpxClient] Giving up after {self._max_retries} retries → {request.url}")
        raise httpx.HTTPStatusError("429 Too Many Requests (max retries)", request=request, response=response)

class SolanaClient:
    def __init__(self, rpc_endpoint: str, max_calls=10, per_seconds=0.9):
        """Initialize Solana client with RPC endpoint.

        Args:
            rpc_endpoint: URL of the Solana RPC endpoint
        """
        self.rpc_endpoint = rpc_endpoint
        self._client = None
        self._cached_blockhash: Hash | None = None
        self._limiter = AsyncRateLimiter(max_calls=max_calls, per_seconds=per_seconds)

    async def get_client(self) -> AsyncClient:
        if self._client is None:
            raw_client = AsyncClient(self.rpc_endpoint)
            patched_httpx = PatchedHttpxClient(base_url=self.rpc_endpoint, timeout=10.0, limiter=self._limiter)
            raw_client._provider.session = patched_httpx
            self._client = raw_client
        return self._client

    async def _execute_with_retry(self, func: Callable[[], Any]) -> Any:
        backoff = ExponentialBackoff()
        while True:
            try:
                result = await func()
                backoff.reset()

                if hasattr(result, "error") and result.error:
                    err = result.error
                    msg = err.get("message") if isinstance(err, dict) else str(err)

                    if "429" in msg or "Too Many Requests" in msg:
                        logger.debug(f"[429] RPC response error: {msg}")
                        await backoff.delay()
                        continue
                    raise Exception(f"RPC error: {msg}")

                return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.debug("[429] HTTPStatusError caught, backing off...")
                    await backoff.delay()
                    continue
                raise

    async def close(self):
        """Close the client connection and stop the blockhash updater."""
        if self._client:
            await self._client.close()
            self._client = None

    async def get_account_info(self, pubkey: Pubkey):
        """Get account info from the blockchain.

        Args:
            pubkey: Public key of the account

        Returns:
            Account info response

        Raises:
            ValueError: If account doesn't exist or has no data
        """
        client = await self.get_client()
        response = await self._execute_with_retry(lambda: client.get_account_info(pubkey, encoding="base64")) # base64 encoding for account data by default
        if not response.value:
            raise ValueError(f"Account {pubkey} not found")
        return response.value

    async def get_token_account_balance(self, token_account: Pubkey) -> int:
        """Get token balance for an account.

        Args:
            token_account: Token account address

        Returns:
            Token balance as integer
        """
        try:
            client = await self.get_client()
            response = await self._execute_with_retry(lambda: client.get_token_account_balance(token_account))
            if response.value:
                return int(response.value.amount)
            return 0
        except Exception as e:
            logger.debug(f"Error while collecting token account balacne: {e}")
            return 0

    async def get_minimum_balance_for_rent_exemption(self, usize: int):
        try:
            client = await self.get_client()
            response = await self._execute_with_retry(lambda: client.get_minimum_balance_for_rent_exemption(usize))
            if response:
                return int(response.value)
            return 3_000_000
        except Exception:
            logger.debug(f"Error while collecting minimum amount for rent, fallback to 3,000,000")
            return 0

    async def get_multiple_accounts_lamports_balances(self, accounts: list[Pubkey]) -> list[int]:
        """Get token balance for an account.

        Args:
            accounts: account addresses

        Returns:
            Token balance as integer
        """
        try:
            client = await self.get_client()
            response = await self._execute_with_retry(lambda: client.get_multiple_accounts(accounts))
            if response.value:
                balances = []
                for i, value in enumerate(response.value):
                    try:
                        balances.append(int(value.lamports))
                    except AttributeError:
                        balances.append(0)
                        continue
                return balances
            return []
        except Exception as e:
            logger.debug(f"Error while collecting multiple accoints lamports balance: {e}")
            return []

    async def get_latest_blockhash(self) -> Hash:
        """Get the latest blockhash.

        Returns:
            Recent blockhash as string
        """
        client = await self.get_client()
        response = await self._execute_with_retry(lambda: client.get_latest_blockhash(commitment=Processed))
        return response.value.blockhash

    async def build_and_send_transaction(
        self,
        *,
        instructions: list[Instruction],
        msg_signer: Keypair,
        signers_keypairs: list[Keypair],
        skip_preflight: bool = True,
        max_retries: int = 3,
        max_confirm_retries: int = 5,
        priority_fee: int | None = None,
        compute_limit: int | None = None,
        label: str = "",
    ) -> tuple[Signature, bool]:
        """
        Send a transaction with optional priority fee.

        Args:
            instructions: List of instructions to include in the transaction.
            skip_preflight: Whether to skip preflight checks.
            msg_signer:
            signers_keypairs:
            max_retries: Maximum number of retry attempts.
            priority_fee: Optional priority fee in microlamports.

        Returns:
            Transaction signature.
        """
        client = await self.get_client()

        if compute_limit is not None:
            compute_limit_ix = set_compute_unit_limit(compute_limit)
            instructions = [compute_limit_ix, *instructions]
        if priority_fee is not None:
            unit_price_ix = set_compute_unit_price(priority_fee)
            instructions = [unit_price_ix, *instructions]

        success = False

        for attempt in range(max_retries):
            try:
                recent_blockhash = await client.get_latest_blockhash()
                message = Message(instructions, msg_signer.pubkey())
                transaction = Transaction(signers_keypairs, message, recent_blockhash.value.blockhash)

                logger.info(f"Transaction size: {len(bytes(transaction))} bytes")

                tx_opts = TxOpts(
                    skip_preflight=skip_preflight, preflight_commitment=Processed
                )
                logger.info(f"Sending {label} TX...")
                response = await self._execute_with_retry(lambda: client.send_transaction(transaction, tx_opts))
                sig = response.value
                success = await self._execute_with_retry(lambda: self.confirm_transaction(signature=sig, max_retries=max_confirm_retries))
                logger.info(f"{label} TX sent: {sig}\nSuccess: {success}")

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.debug(
                        f"Failed to send/ transaction after {max_retries} attempts"
                    )
                    raise

                wait_time = 0.5 ** attempt
                logger.info(
                    f"Transaction attempt {attempt + 1} failed: {e!s}, retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

        return sig, success

    async def simulate_transaction(
        self,
        *,
        instructions: list[Instruction],
        msg_signer: Keypair,
        signers_keypairs: list[Keypair],
    ) -> SimulateTransactionResp:

        client = await self.get_client()
        recent_blockhash = await self._execute_with_retry(lambda: client.get_latest_blockhash())
        message = Message(instructions, msg_signer.pubkey())
        transaction = Transaction(signers_keypairs, message, recent_blockhash.value.blockhash)
        logger.info(f"Transaction size: {len(bytes(transaction))} bytes")

        return await self._execute_with_retry(lambda: client.simulate_transaction(
            transaction,
            sig_verify=True,
        ))

    async def confirm_transaction(
        self, max_retries: int, signature: Signature, commitment: Commitment = Confirmed,
    ) -> bool:
        """Wait for transaction confirmation (3 attempts max)."""
        client = await self.get_client()

        if max_retries == 0:
            return True

        for attempt in range(max_retries):
            try:
                res = await self._execute_with_retry(lambda: client.get_signature_statuses([signature]))
                status = res.value[0]
                if status and status.confirmations is not None:
                    logger.info(f"Confirmed TX {signature} on attempt {attempt + 1}")
                    return True
            except Exception as e:
                logger.debug(f"Error checking status for TX {signature}: {e!s}")
            await asyncio.sleep(1)
        raise RuntimeError(f"TX {signature} not confirmed after {max_retries} attempts")

###################

DECIMALS = 6
MAX_TRANSFER_PER_TX = 7

_client = SolanaClient(rpc_endpoint="https://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2", max_calls=50, per_seconds=1)

class Role(str, Enum):
    dev = "dev"
    fund = "fund"
    group1 = "group1"
    group2 = "group2"
    archive = "archive"


@dataclass
class Wallet:
    """
    Represents a single wallet used in the system.
    """
    name: str
    group: Role
    pubkey: Pubkey
    keypair: Keypair
    ata_address: Optional[Pubkey] = None
    lamports_balance: int = 0
    token_balance: int = 0
    wsol_ata_address = None

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            group=Role(data["group"]),
            name=data["name"],
            pubkey=Pubkey.from_string(data["pubkey"]),
            keypair=Keypair.from_bytes(bytes(data["private_key"])),
        )


RAYDIUM_LAUNCHPAD_PROGRAM_ID = Pubkey.from_string("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")
RAYDIUM_LAUNCHPAD_GLOBAL_CONFIG = Pubkey.from_string("6s1xP3hpbAfFoNtUNF8mfHsjr2Bd97JxFJRWLbL6aHuX")
BONK_PLATFORM_CONFIG = Pubkey.from_string("FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1")
RAYDIUM_LAUNCHPAD_AUTHORITY = Pubkey.from_string("WLHv2UAZm6z4KyaaELi5pjdbJh6RESMva1Rnn8pJVVh")
MPL_TOKEN_METADATA_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")
RENT_PROGRAM_ID = Pubkey.from_string("SysvarRent111111111111111111111111111111111")
EVENT_AUTHORITY = Pubkey.from_string("2DPAtwB8L12vrMRExbLuyGnC7n2J5LNoZQSejeQGpwkr")
WRAPPED_SOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")

POOL_SEED = b"pool"
POOL_VAULT_SEED = b"pool_vault"
METADATA_SEED = b"metadata"

def get_pool_state(base_mint: Pubkey) -> Pubkey:
    result, _ = Pubkey.find_program_address(
        [POOL_SEED, bytes(base_mint), bytes(WRAPPED_SOL_MINT)], RAYDIUM_LAUNCHPAD_PROGRAM_ID)
    return result

def get_pool_vault_address(pool: Pubkey, vault_token_mint: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address(
        [POOL_VAULT_SEED, bytes(pool), bytes(vault_token_mint)], RAYDIUM_LAUNCHPAD_PROGRAM_ID
    )
    return result

@dataclass
class MintInfo:
    pubkey: Pubkey
    pool_state: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey

async def prepare_token_bonk(
    mint_pub: Pubkey,
) -> MintInfo:

    pool = get_pool_state(mint_pub)

    res = MintInfo(
        pubkey=mint_pub,
        pool_state=pool,
        base_vault=get_pool_vault_address(pool, mint_pub),
        quote_vault=get_pool_vault_address(pool, WRAPPED_SOL_MINT),
    )
    logger.info(f"\n\n\nMINT ADDRESS: {res.pubkey}\n\n\n")
    return res

def build_bonk_trade_exact_in_ix(
    *,
    discriminator: bytes,
    payer: Wallet,
    token: MintInfo,
    amount_in: int,
    minimum_amount_out: int = 0,
    share_fee_rate: int = 0,
) -> Instruction:

    data = (
        discriminator +
        struct.pack("<Q", amount_in) +
        struct.pack("<Q", minimum_amount_out) +
        struct.pack("<Q", share_fee_rate)
    )
    accounts = [
        AccountMeta(payer.pubkey, is_signer=True, is_writable=False), #payer
        AccountMeta(RAYDIUM_LAUNCHPAD_AUTHORITY, is_signer=False, is_writable=False), #authority
        AccountMeta(RAYDIUM_LAUNCHPAD_GLOBAL_CONFIG, is_signer=False, is_writable=False), #global_config
        AccountMeta(BONK_PLATFORM_CONFIG, is_signer=False, is_writable=False), #platform_config
        AccountMeta(token.pool_state, is_signer=False, is_writable=True), #pool_state
        AccountMeta(payer.ata_address, is_signer=False, is_writable=True), #user_base_token
        AccountMeta(payer.wsol_ata_address, is_signer=False, is_writable=True), #user_quote_token
        AccountMeta(token.base_vault, is_signer=False, is_writable=True), #base_vault
        AccountMeta(token.quote_vault, is_signer=False, is_writable=True), #quote_vault
        AccountMeta(token.pubkey, is_signer=False, is_writable=False), #base_token_mint
        AccountMeta(WRAPPED_SOL_MINT, is_signer=False, is_writable=False), #quote_token_mint
        AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False), #base_token_program
        AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False), #quote_token_program
        AccountMeta(EVENT_AUTHORITY, is_signer=False, is_writable=False),  # event_authority
        AccountMeta(RAYDIUM_LAUNCHPAD_PROGRAM_ID, is_signer=False, is_writable=False),  # program
    ]

    ix = Instruction(
        program_id=RAYDIUM_LAUNCHPAD_PROGRAM_ID,
        data=data,
        accounts=accounts,
    )
    logger.info(f"{len(bytes(ix))} TRADE IX SIZE")
    return ix


async def transfer_all_to_central(mint_address: str):
    _mint = Pubkey.from_string(mint_address)

    def load_wallets() -> list[Wallet]:
        _wallets = []
        for path in WALLETS_DIR.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
                _wallets.append(Wallet.from_dict(data))
        return _wallets

    all_wallets = load_wallets()
    wallets = [w for w in all_wallets if w.group != Role.fund]
    seller = wallets[0]

    tx_queue: list[tuple[list[Instruction], list[Keypair]]] = []

    current_batch: list[Instruction] = []
    current_signers: set[Keypair] = set()

    for sender in wallets[1:]:
        sender.ata_address = get_associated_token_address(sender.pubkey, _mint)
        seller.ata_address = get_associated_token_address(seller.pubkey, _mint)

        balance = await _client.get_token_account_balance(sender.ata_address)
        if balance <= 0:
            logger.info(f"❌ {sender.name} — нет токенов, пропуск")
            continue

        seller.token_balance += balance

        logger.info(f"🔁 Перевод {balance / 10**DECIMALS} токенов от {sender.name} → {seller.name}")

        ix = transfer_checked(
            TransferCheckedParams(
                program_id=TOKEN_PROGRAM_ID,
                source=sender.ata_address,
                mint=_mint,
                dest=seller.ata_address,
                owner=sender.pubkey,
                amount=balance,
                decimals=DECIMALS,
            )
        )
        current_batch.append(ix)
        current_signers.add(sender.keypair)

        if len(current_batch) >= MAX_TRANSFER_PER_TX:
            tx_queue.append((current_batch[:], list(current_signers)))
            current_batch.clear()
            current_signers.clear()

    if current_batch:
        tx_queue.append((current_batch, list(current_signers)))

    logger.info(f"📦 Собрано {len(tx_queue)} транзакций для отправки")

    for i, (instructions, signers) in enumerate(tx_queue):
        logger.info(f"🚀 Отправка транзакции #{i+1} ({len(instructions)} инструкций)")
        await _client.build_and_send_transaction(
            instructions=instructions,
            msg_signer=signers[0],
            signers_keypairs=signers,
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=20_000,
            label=f"transfer_batch_{i+1}",
        )

    logger.info("✅ Все переводы завершены.")
    await _client.close()

    logger.info("🚀 Запуск продажи токенов...")
    await sell_tokens(seller, _mint)

SELL_EXACT_IN: [bytes] = bytes([149, 39, 222, 155, 211, 124, 152, 26])

async def sell_tokens(seller: Wallet, mintik: Pubkey):
    seller.wsol_ata_address = get_associated_token_address(
        owner=seller.pubkey,
        mint=WRAPPED_SOL_MINT,
    )

    expected_amount = seller.token_balance

    for attempt in range(10):
        current_amount = await _client.get_token_account_balance(seller.ata_address)
        logger.info(f"Ожидается {expected_amount / 10 ** DECIMALS}, на балансе {current_amount / 10 ** DECIMALS}")
        if current_amount >= expected_amount * 0.95:
            break
        await asyncio.sleep(0.8)
    else:
        raise RuntimeError("❌ Баланс не поступил в течение 10 попыток")

    sell_ix = build_bonk_trade_exact_in_ix(
        discriminator=SELL_EXACT_IN,
        payer=seller,
        token=await prepare_token_bonk(mintik),
        amount_in=current_amount,
    )
    create_wsol_ata = create_idempotent_associated_token_account(
        payer=seller.pubkey,
        owner=seller.pubkey,
        mint=WRAPPED_SOL_MINT,
    )

    input("Баланс готов, нажмите Enter")
    try:
        await _client.build_and_send_transaction(
            instructions=[create_wsol_ata, sell_ix],
            msg_signer=seller.keypair,
            signers_keypairs=[seller.keypair],
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=50_000,
            label=f"Sell All",
        )
    except Exception as e:
        logger.error(e)
        return


if __name__ == "__main__":
    mint = input("Введите mint address токена: ").strip()
    asyncio.run(transfer_all_to_central(mint))
