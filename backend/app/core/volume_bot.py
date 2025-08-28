from __future__ import annotations

import contextlib
import asyncio
import random
from dataclasses import dataclass, field

from solders.keypair import Keypair
from solders.instruction import Instruction

from .data_collector import DataCollector
from ..core.wallet_manager import Wallet
from ..core.client import SolanaClient
from ..core.logger import logger
from ..core.constants import LAMPORTS_PER_SOL
from ..services.tokens import get_token
from ..services.buyer import _calculate_req_tokens_for_buyer, buy_token_prepare_instruction
from ..services.seller import _calculate_req_tokens_for_seller, sell_token_prepare_instruction

MIN_INSTRUCTION_PER_TX = 1
MAX_INSTRUCTION_PER_TX = 5

def sol_to_lamports(sol: float) -> int:
    return int(sol * LAMPORTS_PER_SOL)

@dataclass
class VolumeBotConfig:
    min_sol: float
    max_sol: float
    buy_bias: float = 0.5
    wallets: list[Wallet] = field(default_factory=list)

class VolumeBot:
    """
    Имитация объёма: случайные buy/sell на пуле кошельков.
    Управляется методами start/pause/stop + bias up/down.
    """

    def __init__(
        self,
        cfg: VolumeBotConfig,
        dc: DataCollector,
        sol_client: SolanaClient,
    ) -> None:
        self.cfg = cfg
        self.dc = dc
        self.sol_client = sol_client

        self.rand = random.Random()
        self._run_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            logger.info("VolumeBot already running")
            return
        self._run_event.set()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._worker())
        logger.info("VolumeBot started")

    def pause(self) -> None:
        self._run_event.clear()
        logger.info("VolumeBot paused")

    def resume(self) -> None:
        self._run_event.set()
        logger.info("VolumeBot resumed")

    async def stop(self) -> None:
        self._stop_event.set()
        self._run_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("VolumeBot stopped")

    def bias_up(self, step: float = 0.05) -> float:
        self.cfg.buy_bias = min(0.99, self.cfg.buy_bias + step)
        return self.cfg.buy_bias

    def bias_down(self, step: float = 0.05) -> float:
        self.cfg.buy_bias = max(0.01, self.cfg.buy_bias - step)
        return self.cfg.buy_bias

    def get_status(self) -> dict:
        return {
            "running": self._task is not None and not self._task.done(),
            "paused": not self._run_event.is_set(),
            "buy_bias": self.cfg.buy_bias,
        }

    async def _worker(self) -> None:
        ix_batch: list[Instruction] = []
        signers_batch: list[Keypair] = []
        token_info = await get_token()
        while not self._stop_event.is_set():
            await self._run_event.wait()
            wallet = self.rand.choice(self.cfg.wallets)
            sol_amount = self.rand.uniform(self.cfg.min_sol, self.cfg.max_sol)
            is_buy = self.rand.random() < self.cfg.buy_bias
            try:
                if is_buy:
                    buyer = await _calculate_req_tokens_for_buyer(
                        wallet=wallet,
                        token_info=token_info,
                        dc=self.dc,
                        sol_amount=sol_amount,
                    )
                    ix = await buy_token_prepare_instruction(
                        token_info=token_info,
                        buyer=buyer,
                    )
                else:
                    seller = await _calculate_req_tokens_for_seller(
                        wallet=wallet,
                        token_info=token_info,
                        dc=self.dc,
                        sol_amount=sol_amount,
                    )
                    ix = await sell_token_prepare_instruction(
                        token_info=token_info,
                        seller=seller,
                    )
            except Exception as e:
                logger.error(f"Failed to build {'BUY' if is_buy else 'SELL'} ix: {e}")
                await asyncio.sleep(self.rand.uniform(0.3, 1.0))
                continue

            ix_batch.append(ix)
            signers_batch.append(wallet.keypair)

            max_instr = self.rand.randint(MIN_INSTRUCTION_PER_TX, MAX_INSTRUCTION_PER_TX)

            if len(ix_batch) >= max_instr:
                await self._send_batch(ix_batch[:max_instr],
                                       signers_batch[:max_instr])
                ix_batch.clear()
                signers_batch.clear()

            await asyncio.sleep(self.rand.uniform(0.05, 0.015))

        if ix_batch:
            await self._send_batch(ix_batch, signers_batch)

    async def _send_batch(
        self,
        ix_list: list[Instruction],
        signers: list[Keypair],
    ) -> None:
        try:
            await self.sol_client.build_and_send_transaction(
                instructions=ix_list,
                msg_signer=signers[0],
                signers_keypairs=signers,
                label="Volume batch",
                max_retries=1,
                max_confirm_retries=0,
            )
        except Exception as e:
            logger.error(f"VolumeBot TX error: {e}")
