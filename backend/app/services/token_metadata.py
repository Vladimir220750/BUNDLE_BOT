from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from spl.token.constants import TOKEN_2022_PROGRAM_ID
from construct import Struct, Bytes, Int32ul
from construct import Container

METADATA_DISCRIMINATOR = bytes.fromhex("d2e11ea258b84d8d")

MetadataStruct = Struct(
    "discriminator" / Bytes(8),
    "name" / Int32ul >> Bytes(lambda ctx: len(ctx._.name.encode("utf-8"))),
    "symbol" / Int32ul >> Bytes(lambda ctx: len(ctx._.symbol.encode("utf-8"))),
    "uri" / Int32ul >> Bytes(lambda ctx: len(ctx._.uri.encode("utf-8"))),
)

METADATA_POINTER_DISCRIMINATOR = 39
METADATA_POINTER_SUB_DISCRIMINATOR = 0

def encode_zeroable_option(pubkey: Pubkey | None) -> bytes:
    if pubkey is None:
        return b'\x00' * 32
    return bytes(pubkey)

def build_initialize_metadata_pointer_ix(
    mint: Pubkey,
    authority: Pubkey | None,
    metadata_address: Pubkey | None,
) -> Instruction:
    data = bytes([
        METADATA_POINTER_DISCRIMINATOR,
        METADATA_POINTER_SUB_DISCRIMINATOR
    ]) + encode_zeroable_option(authority) + encode_zeroable_option(metadata_address)

    return Instruction(
        program_id=TOKEN_2022_PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        ],
        data=data
    )


def encode_string(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return Int32ul.build(len(encoded)) + encoded

def build_initialize_token_metadata_ix(
    metadata: Pubkey,
    update_authority: Pubkey,
    mint: Pubkey,
    mint_authority: Pubkey,
    name: str,
    symbol: str,
    uri: str
) -> Instruction:
    data = (
        METADATA_DISCRIMINATOR +
        encode_string(name) +
        encode_string(symbol) +
        encode_string(uri)
    )

    return Instruction(
        program_id=TOKEN_2022_PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=metadata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=update_authority, is_signer=False, is_writable=False),
            AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=mint_authority, is_signer=True, is_writable=False),
        ],
        data=data
    )

