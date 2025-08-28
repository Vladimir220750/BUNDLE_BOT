import httpx
import base64
import asyncio
import time
from collections import deque
from inspect import Signature
from typing import Any, Coroutine

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed, Commitment, Confirmed
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.solders import Signature, SimulateTransactionResp
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams

from .logger import logger

class SolanaClient:
    class _RLProxy:
        def __init__(self, limiter, rpc):
            self._limiter, self._rpc = limiter, rpc

        def __getattr__(self, name):
            attr = getattr(self._rpc, name)

            if not callable(attr):
                return attr

            async def wrapped(*args, **kwargs):
                await self._limiter.wait()
                return await attr(*args, **kwargs)

            return wrapped

    class _AsyncRateLimiter:
        def __init__(self, max_calls: int, per_seconds: float):
            self.max_calls = max_calls
            self.per_seconds = per_seconds
            self.calls = deque()

        async def wait(self):
            now = time.monotonic()
            while len(self.calls) >= self.max_calls:
                elapsed = now - self.calls[0]
                if elapsed < self.per_seconds:
                    print(f"slip")
                    wait_time = self.per_seconds - elapsed
                    await asyncio.sleep(min(wait_time, 0.01))
                    now = time.monotonic()
                else:
                    self.calls.popleft()
            self.calls.append(now)


    def __init__(self, rpc_endpoint: str):
        """Initialize Solana client with RPC endpoint.

        Args:
            rpc_endpoint: URL of the Solana RPC endpoint
        """
        self.rpc_endpoint = rpc_endpoint
        self._client = None
        self._cached_blockhash: Hash | None = None
        self._limiter = self._AsyncRateLimiter(max_calls=20, per_seconds=1.0)

    async def get_client(self) -> AsyncClient:
        """Get or create the AsyncClient instance.

        Returns:
            AsyncClient instance
        """
        if self._client is None:
            raw_client = AsyncClient(self.rpc_endpoint)
            self._client = self._RLProxy(self._limiter, raw_client)

        return self._client

    async def close(self):
        """Close the client connection and stop the blockhash updater."""
        if self._client:
            await self._client._rpc.close()
            self._client = None

    async def get_account_info(self, pubkey: Pubkey, encoding="base64"):
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
                return response
            else:
                response = await client.get_account_info(pubkey, encoding=encoding) # base64 encoding for account data by default
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
            response = await client.get_token_account_balance(token_account)
            if response.value:
                logger.info(f"[SolanaClient] successful fetch token account balance: {int(response.value.amount)}")
                return int(response.value.amount)
            return 0
        except Exception as e:
            return 0

    async def get_multiple_accounts_lamports_balances(self, accounts: list[Pubkey]) -> list[int]:
        """Get token balance for an account.

        Args:
            accounts: account addresses

        Returns:
            Token balance as integer
        """
        client = await self.get_client()
        response = await client.get_multiple_accounts(accounts)
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

    async def get_latest_blockhash(self) -> Hash:
        """Get the latest blockhash.

        Returns:
            Recent blockhash as string
        """
        client = await self.get_client()
        response = await client.get_latest_blockhash(commitment=Processed)
        return response.value.blockhash

    async def build_and_send_transaction(
        self,
        *,
        instructions: list[Instruction],
        msg_signer: Keypair,
        signers_keypairs: list[Keypair],
        skip_preflight: bool = True,
        max_retries: int = 3,
        priority_fee: int | None = None,
        compute_limit: int | None = None,
        label: str = "",
        jito_tip: int = 0,
    ) -> Signature | None:
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

        for attempt in range(max_retries):
            try:
                recent_blockhash = await client.get_latest_blockhash()

                if JITO:  # Minimum lamports to Jito
                    tip_ix = transfer(
                        TransferParams(
                            from_pubkey=msg_signer.pubkey(),
                            to_pubkey=JITO_TIP_ACCOUNT,
                            lamports=jito_tip
                        )
                    )
                    instructions = [tip_ix, *instructions]

                message = Message(instructions, msg_signer.pubkey())
                transaction = Transaction(signers_keypairs, message, recent_blockhash.value.blockhash)

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
                        success = f"Check status manual: https://solscan.io/tx/{sig}"
                else:
                    response = await client.send_transaction(transaction, tx_opts)
                    sig = response.value
                    success = await self.confirm_transaction(signature=sig)
                logger.info(f"Transaction size: {len(bytes(transaction))} bytes")
                logger.info(f"{label} TX sent: {sig}\nSuccess: {success}")

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to send/ transaction after {max_retries} attempts"
                    )
                    raise
                wait_time = 2**attempt
                logger.warning(
                    f"Transaction attempt {attempt + 1} failed: {e!s}, retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

    async def send_jito_bundle_transactions(
        self,
        *,
        transactions: list[str],
    ):
        JITO_RPC_BUNDLE_SEND_TX = "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/bundles"

        async with httpx.AsyncClient() as _cl:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [
                    transactions,
                    {
                        "encoding": "base64"
                    }
                ]
            }
            print(payload)
            resp = await _cl.post(f"{JITO_RPC_BUNDLE_SEND_TX}", json=payload)
            if resp.status_code != 200:
                raise Exception(f"Jito returned HTTP {resp.status_code}: {resp.text}")
            result = resp.json()
            if "error" in result:
                raise Exception(f"Jito RPC error: {result['error']}")
            sig = result["result"]
            logger.info(f"Check status manual: https://solscan.io/tx/{sig}")

    async def _build_raw_transaction_jito(
        self,
        *,
        instructions: list[Instruction],
        msg_signer: Keypair,
        signers_keypairs: list[Keypair],
        priority_fee: int | None = None,
        compute_limit: int | None = None,
        label: str = "",
        jito_tip: int = 0,
    ) -> str:

        logger.info(f"Building {label} JITO TX...")

        JITO_TIP_ACCOUNT = Pubkey.from_string("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")

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

        recent_blockhash = await client.get_latest_blockhash()

        if jito_tip > 0:
            tip_ix = transfer(
                    TransferParams(
                        from_pubkey=msg_signer.pubkey(),
                        to_pubkey=JITO_TIP_ACCOUNT,
                        lamports=jito_tip
                    )
                )
            instructions = [tip_ix, *instructions]

        message = Message(instructions, msg_signer.pubkey())
        transaction = Transaction(signers_keypairs, message, recent_blockhash.value.blockhash)

        logger.info(f"Transaction size: {len(bytes(transaction))} bytes")
        b64_tx = base64.b64encode(bytes(transaction)).decode("utf-8")

        return b64_tx

    async def simulate_transaction(
        self,
        *,
        instructions: list[Instruction],
        msg_signer: Keypair,
        signers_keypairs: list[Keypair],
    ) -> SimulateTransactionResp:

        client = await self.get_client()
        recent_blockhash = await client.get_latest_blockhash()
        message = Message(instructions, msg_signer.pubkey())
        transaction = Transaction(signers_keypairs, message, recent_blockhash.value.blockhash)
        logger.info(f"Transaction size: {len(bytes(transaction))} bytes")

        return await client.simulate_transaction(
            transaction,
            sig_verify=True,
        )

    async def confirm_transaction(
        self, signature: Signature, commitment: Commitment = Confirmed
    ) -> bool:
        """Wait for transaction confirmation (3 attempts max)."""
        client = await self.get_client()

        for attempt in range(10):
            try:
                res = await client.get_signature_statuses([signature])
                status = res.value[0]
                if status and status.confirmations is not None:
                    logger.info(f"Confirmed TX {signature} on attempt {attempt + 1}")
                    return True
            except Exception as e:
                logger.warning(f"Error checking status for TX {signature}: {e!s}")
            await asyncio.sleep(1)

        logger.warning(f"TX {signature} not confirmed after 10 attempts")
        raise
