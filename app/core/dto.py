from dataclasses import dataclass
from typing import Optional

from solders.pubkey import Pubkey
from solders.solders import Keypair

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
class TokenDTO:
    name: str
    symbol: str
    uri: str
    keypair: Keypair
