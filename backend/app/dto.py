from dataclasses import dataclass
import typing
from pydantic import BaseModel, field_validator, condecimal
from fastapi import UploadFile, Form

from solders.pubkey import Pubkey
from solders.solders import Keypair

from .enums import Role

PositiveSol = condecimal(gt=0, max_digits=18, decimal_places=9)


class WalletsCreateRequest(BaseModel):
    dev: bool = False
    fund: bool = False
    group1: int | None = None
    group2: int | None = None


class GroupBuyRequest(BaseModel):
    group: Role
    amount: float


class GroupSellRequest(BaseModel):
    group: Role
    percent: int


class InitializeBuyTokensRequest(BaseModel):
    dev: typing.Optional[int] = 0
    group1: typing.Optional[int] = 0

    @field_validator("dev", "group1", mode="before")
    @classmethod
    def multiply_by_million(cls, v):
        if v is None:
            return 0
        return int(v) * 1_000_000

class DistributeRequest(BaseModel):
    """
    Map of destination pubkey -> amount of SOL to send.
    Amounts must be positive.
    """
    transfers: dict[str, float]


class WalletDTO(BaseModel):
    address: str
    group: str
    name: str
    sol_balance: float = 0
    token_balance: float = 0

class TokenDTO(BaseModel):
    name: str
    symbol: str
    uri: str
    mint_address: str
    private_key: list[int]
    bonding_curve: str
    associated_bonding_curve: str
    token_creator_vault: str
    metadata: str

class RaydiumTokenDTO(BaseModel):
    name: str
    symbol: str
    uri: str
    mint_address: str
    private_key: list[int]
    transfer_fee_authority_kp: list[int]
    tax: int
    supply: int
    mint_authority: bool
    freeze_authority: bool

class UpdateTokenRequest(BaseModel):
    mint: str

class TokenCreateRequest(BaseModel):
    name: str = Form(...)
    symbol: str = Form(...)
    description: str = Form(...)
    telegram: str = Form(...)
    twitter: str = Form(...)
    website: str = Form(...)
    image: UploadFile

class CreateTokenRaydiumRequest(BaseModel):
    name: str = Form(...)
    symbol: str = Form(...)
    description: str = Form(...)
    supply: int = Form(...)
    tax: int = Form(...)
    freeze_authority: bool = Form(...)
    mint_authority: bool = Form(...)
    telegram: str = Form(...)
    twitter: str = Form(...)
    website: str = Form(...)
    image: UploadFile

class DataDTO(BaseModel):
    wallet: WalletDTO
    liq: float
    clear_liq: float
    mcap: int


class VolumeStartRequest(BaseModel):
    min_sol: float
    max_sol: float

class ArchiveWalletRequest(BaseModel):
    wallet_pub: str


class CONFIGDTO(BaseModel):
    initial_balance: float = 0.0
    image_links: list[str] = []

class MintToRequest(BaseModel):
    mint: str
    amount: int
    dest: typing.Optional[str] = None

class BuildSwapInstructionRequest(BaseModel):
    wallet: dict
    amount: int
    is_buy: bool

class CopyTokenResponse(BaseModel):
    name: typing.Optional[str]
    symbol: typing.Optional[str]
    description: typing.Optional[str]
    telegram: typing.Optional[str]
    twitter: typing.Optional[str]
    website: typing.Optional[str]

class WitdrawFeeRequest(BaseModel):
    witdraw_authority_kp: str
    destination: typing.Optional[str]

class UpdateTransferFeeConfigRequest(BaseModel):
    config: dict

class SetWithdrawAuthorityRequest(BaseModel):
    old_kp: str
    new_kp: str
    mint: str

class HideSupplyRequest(BaseModel):
    dev: dict
    amount_after: int # UI, millions
    mint: str
    initial_supply_ui: int