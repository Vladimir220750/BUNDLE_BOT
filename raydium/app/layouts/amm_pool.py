from construct import Struct, Int8ul, Int16ub, Int64ul, Bytes, Array

PUBKEY_LAYOUT = Bytes(32)

AmmConfigLayout = Struct(
    "bump" / Int8ul,
    "disable_create_pool" / Int8ul,
    "index" / Int16ub,
    "trade_fee_rate" / Int64ul,
    "protocol_fee_rate" / Int64ul,
    "fund_fee_rate" / Int64ul,
    "create_pool_fee" / Int64ul,
    "protocol_owner" / PUBKEY_LAYOUT,
    "fund_owner" / PUBKEY_LAYOUT,
    "padding" / Array(16, Int64ul),
)

PoolStateLayout = Struct(
    "amm_config" / PUBKEY_LAYOUT,
    "pool_creator" / PUBKEY_LAYOUT,
    "token_0_vault" / PUBKEY_LAYOUT,
    "token_1_vault" / PUBKEY_LAYOUT,
    "lp_mint" / PUBKEY_LAYOUT,
    "token_0_mint" / PUBKEY_LAYOUT,
    "token_1_mint" / PUBKEY_LAYOUT,
    "token_0_program" / PUBKEY_LAYOUT,
    "token_1_program" / PUBKEY_LAYOUT,
    "observation_key" / PUBKEY_LAYOUT,
    "auth_bump" / Int8ul,
    "status" / Int8ul,
    "lp_mint_decimals" / Int8ul,
    "mint_0_decimals" / Int8ul,
    "mint_1_decimals" / Int8ul,
    "lp_supply" / Int64ul,
    "protocol_fees_token_0" / Int64ul,
    "protocol_fees_token_1" / Int64ul,
    "fund_fees_token_0" / Int64ul,
    "fund_fees_token_1" / Int64ul,
    "open_time" / Int64ul,
    "recent_epoch" / Int64ul,
    "padding" / Array(31, Int64ul),
)

ObservationLayout = Struct(
    "block_timestamp" / Int64ul,
    "cumulative_token_0_price_x32" / Int64ul, # чат здесь тсавил 128
    "cumulative_token_1_price_x32" / Int64ul, # аналогично
)

ObservationStateLayout = Struct(
    "initialized" / Int8ul,
    "observation_index" / Int16ub,
    "pool_id" / PUBKEY_LAYOUT,
    "observations" / Array(100, ObservationLayout),
    "padding" / Array(4, Int64ul),
)
