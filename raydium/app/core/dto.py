from dataclasses import dataclass
from typing import List, Optional, Any
from pydantic import BaseModel

from solders.pubkey import Pubkey
from solders.solders import Keypair, Instruction
from base64 import b64encode

from .constants import LAMPORTS_PER_SOL
from .enum import Role


@dataclass
class AmmConfig:
    bump: int
    disable_create_pool: int
    index: int
    trade_fee_rate: int
    protocol_fee_rate: int
    fund_fee_rate: int
    create_pool_fee: int
    protocol_owner: Pubkey
    fund_owner: Pubkey

@dataclass
class PoolState:
    amm_config: Pubkey
    pool_creator: Pubkey
    token_0_vault: Pubkey
    token_1_vault: Pubkey
    lp_mint: Pubkey
    token_0_mint: Pubkey
    token_1_mint: Pubkey
    token_0_program: Pubkey
    token_1_program: Pubkey
    observation_key: Pubkey
    auth_bump: int
    status: int
    lp_mint_decimals: int
    mint_0_decimals: int
    mint_1_decimals: int
    lp_supply: int
    protocol_fees_token_0: int
    protocol_fees_token_1: int
    fund_fees_token_0: int
    fund_fees_token_1: int
    open_time: int
    recent_epoch: int

@dataclass
class Observation:
    block_timestamp: int
    cumulative_token_0_price_x32: int
    cumulative_token_1_price_x32: int

@dataclass
class ObservationState:
    initialized: int
    observation_index: int
    pool_id: Pubkey
    observations: List[Observation]

@dataclass
class LiquidityPoolData:
    creator_kp: Keypair
    token_mint0: Pubkey
    token_mint1: Pubkey
    token_0_program: Pubkey
    token_1_program: Pubkey
    token_mint0_amount: int
    token_mint1_amount: int

    pool_state: Pubkey
    authority: Pubkey
    lp_mint: Pubkey
    creator_lp_token: Pubkey
    token0_vault: Pubkey
    token1_vault: Pubkey
    observation: Pubkey

    creator_token0: Pubkey
    creator_token1: Pubkey
    token_0_ata: Pubkey
    token_1_ata: Pubkey
    liq_vault: Pubkey
    initialized: Optional[bool] = None
    random_pool_id: Optional[Pubkey] = None
    lp_amount: int = 0

    def to_json_dict(self) -> dict:
        return {
            **{field: str(getattr(self, field)) for field in (
                "token_mint0", "token_mint1", "token_0_program", "token_1_program",
                "pool_state", "authority", "lp_mint", "creator_lp_token", "token0_vault",
                "token1_vault", "observation", "creator_token0", "creator_token1", "token_0_ata",
                "token_1_ata", "liq_vault",
            )},
            "creator": list(self.creator_kp.to_bytes()),
            "token_mint0_amount": self.token_mint0_amount,
            "token_mint1_amount": self.token_mint1_amount,
            "random_pool_id": str(self.random_pool_id) if self.random_pool_id else None,
            "initialized": self.initialized,
            "lp_amount": self.lp_amount
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "LiquidityPoolData":
        return cls(
            creator_kp=Keypair.from_bytes(bytes(data["creator"])),
            token_mint0=Pubkey.from_string(data["token_mint0"]),
            token_mint1=Pubkey.from_string(data["token_mint1"]),
            token_0_program=Pubkey.from_string(data["token_0_program"]),
            token_1_program=Pubkey.from_string(data["token_1_program"]),
            token_mint0_amount=int(data["token_mint0_amount"]),
            token_mint1_amount=int(data["token_mint1_amount"]),
            pool_state=Pubkey.from_string(data["pool_state"]),
            authority=Pubkey.from_string(data["authority"]),
            lp_mint=Pubkey.from_string(data["lp_mint"]),
            creator_lp_token=Pubkey.from_string(data["creator_lp_token"]),
            token0_vault=Pubkey.from_string(data["token0_vault"]),
            token1_vault=Pubkey.from_string(data["token1_vault"]),
            observation=Pubkey.from_string(data["observation"]),
            creator_token0=Pubkey.from_string(data["creator_token0"]),
            creator_token1=Pubkey.from_string(data["creator_token1"]),
            token_0_ata=Pubkey.from_string(data["token_0_ata"]),
            token_1_ata=Pubkey.from_string(data["token_1_ata"]),
            liq_vault=Pubkey.from_string(data["liq_vault"]),
            initialized=data["initialized"],
            random_pool_id=Pubkey.from_string(data["random_pool_id"]) if data["random_pool_id"] else None,
            lp_amount=int(data["lp_amount"])
        )

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

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            group=Role(data["group"]),
            name=data["name"],
            pubkey=Pubkey.from_string(data["pubkey"]),
            keypair=Keypair.from_base58_string(data["private_key"]),
            lamports_balance=data["balance"] / LAMPORTS_PER_SOL
        )

class SerializedAccountMeta(BaseModel):
    pubkey: str
    is_signer: bool
    is_writable: bool

class SerializedInstruction(BaseModel):
    program_id: str
    accounts: list[SerializedAccountMeta]
    data: str

    @classmethod
    def from_instruction(cls, instr: Instruction) -> "SerializedInstruction":
        return cls(
            program_id=str(instr.program_id),
            accounts=[
                SerializedAccountMeta(
                    pubkey=str(meta.pubkey),
                    is_signer=meta.is_signer,
                    is_writable=meta.is_writable,
                )
                for meta in instr.accounts
            ],
            data=b64encode(instr.data).decode(),
        )

class InitializeRequest(BaseModel):
    dev_wallet: dict
    sniper_wallets: list[dict]
    token_amount_ui: int
    wsol_amount_ui: float
    snipe_amount_ui: Optional[float] = None
    created_token_sting: str
    transfer_fee: int = 0


class CONFIGDTO(BaseModel):
    initial_balance: float = 0.0
    image_links: list[str] = []

class BuildSwapInstructionRequest(BaseModel):
    wallet: dict
    amount: int
    is_buy: bool