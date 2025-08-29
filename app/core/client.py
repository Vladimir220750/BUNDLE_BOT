import base64
import httpx
import asyncio
import time
import random
from collections import deque
from collections.abc import Callable
from inspect import Signature
from typing import Any, Optional
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed, Commitment, Confirmed
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.solders import SimulateTransactionResp, AccountJSON, Account
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams

from .logger import logger

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
        logger.warning(f"[Backoff] Sleeping for {delay:.2f}s due to rate limit...")
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

            logger.warning(f"[PatchedHttpxClient] 429 Too Many Requests → attempt {attempt+1}/{self._max_retries} for {request.url}")
            await self._backoff.delay()

        logger.error(f"[PatchedHttpxClient] Giving up after {self._max_retries} retries → {request.url}")
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

        self._cached_blockhash: Optional[Hash] = None
        self._cached_blockhash_ts: float = 0.0
        self._blockhash_ttl_s: float = 15.0

    async def _fetch_blockhash(self, commitment=Processed) -> Hash:
        client = await self.get_client()
        resp = await self._execute_with_retry(lambda: client.get_latest_blockhash(commitment=commitment))
        bh: Hash = resp.value.blockhash
        self._cached_blockhash = bh
        self._cached_blockhash_ts = time.monotonic()
        logger.debug(f"[blockhash] fetched: {bh}")
        return bh

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
                        logger.warning(f"[429] RPC response error: {msg}")
                        await backoff.delay()
                        continue
                    raise Exception(f"RPC error: {msg}")

                return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("[429] HTTPStatusError caught, backing off...")
                    await backoff.delay()
                    continue
                raise

    async def close(self):
        """Close the client connection and stop the blockhash updater."""
        if self._client:
            await self._client.close()
            self._client = None

    async def get_account_info(self, pubkey: Pubkey, encoding="base64") -> AccountJSON | Account:
        """Get account info from the blockchain.

        Args:
            pubkey: Public key of the account

        Returns:
            Account info response

        Raises:
            ValueError: If account doesn't exist or has no data
        """
        client = await self.get_client()
        try:
            if encoding == "jsonParsed":
                response = await client.get_account_info_json_parsed(pubkey)
                if not response.value:
                    raise ValueError(f"Account {pubkey} not found")
                return response.value
            else:
                response = await client.get_account_info(pubkey,
                                                         encoding=encoding)  # base64 encoding for account data by default
                if not response.value:
                    raise ValueError(f"Account {pubkey} not found")
                return response.value
        except Exception as e:
            logger.error(f"Errow while collecting account info {encoding}: {e}")

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
            return 3_000_000

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
            logger.warning(f"Error while collecting multiple accoints lamports balance: {e}")
            return []

    async def get_latest_blockhash(self, *, commitment=Processed) -> Hash:
        """Возвращает blockhash с кэшем 15s."""
        now = time.monotonic()
        if self._cached_blockhash is None or (now - self._cached_blockhash_ts) > self._blockhash_ttl_s:
            return await self._fetch_blockhash(commitment=commitment)
        return self._cached_blockhash

    async def build_signed_raw_transaction(
        self,
        *,
        instructions: list[Instruction],
        payer: Keypair,
        signers: list[Keypair] | None = None,
        priority_fee_microlamports: Optional[int] = None,
        compute_unit_limit: Optional[int] = None,
    ) -> bytes:
        """
        Собирает Message, добавляет ComputeBudget (опционально), берёт кэшированный blockhash,
        подписывает и возвращает сериализованные байты транзакции.
        """
        if signers is None:
            signers = [payer]
        else:
            if payer not in signers:
                signers = [payer, *signers]

        ixs: list[Instruction] = []
        if compute_unit_limit is not None:
            ixs.append(set_compute_unit_limit(compute_unit_limit))
        if priority_fee_microlamports is not None:
            ixs.append(set_compute_unit_price(priority_fee_microlamports))
        ixs.extend(instructions)

        blockhash: Hash = await self.get_latest_blockhash()
        msg = Message(ixs, payer.pubkey())
        tx = Transaction(signers, msg, blockhash)
        raw = bytes(tx)

        if len(raw) > 1232:
            logger.info(len(raw))
            return bytes()

        logger.debug(f"[TX] built size={len(raw)} bytes; signers={len(signers)}")
        return raw

    async def send_raw_transaction(self, raw_tx: bytes, *, skip_preflight: bool = True) -> str:
        """
        Отправляет сырую транзакцию. Возвращает signature (str).
        """
        client = await self.get_client()
        opts = TxOpts(skip_preflight=skip_preflight, preflight_commitment=Processed)
        await self._execute_with_retry(lambda: client.send_raw_transaction(raw_tx, opts=opts))
        sig = Transaction.from_bytes(raw_tx).signatures[0]
        logger.info(f"[TX] raw sent: {str(sig)}")
        return str(sig)

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
        jito_tip: int = 0,
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
        JITO = False
        if jito_tip >= 1000:
            JITO = True

        JITO_TIP_ACCOUNT = Pubkey.from_string("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")
        JITO_RPC_SEND_TX = "https://mainnet.block-engine.jito.wtf/api/v1/transactions"

        client = await self.get_client()

        logger.info(
            f"Priority fee in microlamports: {priority_fee if priority_fee else 0}"
        )

        if compute_limit is not None:
            compute_limit_ix = set_compute_unit_limit(compute_limit)
            instructions = [compute_limit_ix, *instructions]
        if priority_fee is not None:
            unit_price_ix = set_compute_unit_price(priority_fee)
            instructions = [unit_price_ix, *instructions]

        recent_blockhash = await self.get_latest_blockhash()

        if JITO: # Minimum lamports to Jito
            tip_ix = transfer(
                TransferParams(
                    from_pubkey=msg_signer.pubkey(),
                    to_pubkey=JITO_TIP_ACCOUNT,
                    lamports=jito_tip
                )
            )
            instructions = [tip_ix, *instructions]

        message = Message(instructions, msg_signer.pubkey())
        transaction = Transaction(signers_keypairs, message, recent_blockhash)

        logger.info(f"Transaction size: {len(bytes(transaction))} bytes")
        success = False

        for attempt in range(max_retries):
            try:
                tx_opts = TxOpts(
                    skip_preflight=skip_preflight, preflight_commitment=Processed
                )
                logger.info(f"Sending {label} TX...")
                if JITO:
                    b64_tx = base64.b64encode(bytes(transaction)).decode("utf-8")

                    async with httpx.AsyncClient() as _cl:
                        payload = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "sendTransaction",
                            "params": [
                                b64_tx,
                                {
                                    "encoding": "base64"
                                }
                            ]
                        }

                    resp = await _cl.post(f"{JITO_RPC_SEND_TX}?bundleOnly=true", json=payload)
                    if resp.status_code != 200:
                        raise Exception(f"Jito returned HTTP {resp.status_code}: {resp.text}")

                    result = resp.json()
                    if "error" in result:
                        raise Exception(f"Jito RPC error: {result['error']}")
                    sig = result["result"]
                    await self._execute_with_retry(lambda: self.confirm_transaction(signature=sig, max_retries=max_confirm_retries))

                else:
                    response = await self._execute_with_retry(lambda: client.send_transaction(transaction, tx_opts))
                    sig = response.value
                    success = await self._execute_with_retry(lambda: self.confirm_transaction(signature=sig, max_retries=max_confirm_retries))
                    logger.info(f"{label} TX sent: {sig}\nSuccess: {success}")

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to send/ transaction after {max_retries} attempts"
                    )
                    raise

                wait_time = 0.5 ** attempt
                logger.warning(
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
        recent_blockhash = await self._execute_with_retry(lambda: self.get_latest_blockhash())
        message = Message(instructions, msg_signer.pubkey())
        transaction = Transaction(signers_keypairs, message, recent_blockhash)
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
                logger.warning(f"Error checking status for TX {signature}: {e!s}")
            await asyncio.sleep(1)

        logger.warning(f"TX {signature} not confirmed after {max_retries} attempts")
        raise