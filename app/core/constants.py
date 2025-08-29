from solders.pubkey import Pubkey

RAYDIUM_CP_PROGRAM_ID = Pubkey.from_string("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")
ADMIN_ID = Pubkey.from_string("GThUX1Atko4tqhN2NaiTazWSeFWMuiUvfFnyJyUghFMJ")
CREATE_POOL_FEE_RECEIVER_ID = Pubkey.from_string("DNXgeM9EiiaAbaWvwjHj9fQQLAX5ZsfHyvmYUNRAdNC8")
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_PROGRAM_2022_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPv1111111111111111111111111111111111")
ASSOCIATED_TOKEN_ACCOUNT_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYS_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")
SYS_VAR_RENT_ID = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

SOL_WRAPPED_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")

AMM_CONFIG_SEED = b"amm_config"
POOL_SEED = b"pool"
POOL_LP_MINT_SEED = b"pool_lp_mint"
POOL_VAULT_SEED = b"pool_vault"
AUTH_SEED = b"vault_and_lp_mint_auth_seed"
OBSERVATION_SEED = b"observation"

INITIALIZE_DISCRIMINATOR = bytes.fromhex("afaf6d1f0d989bed")
SWAP_BASE_INPUT_DISCRIMINATOR = bytes.fromhex("8fbe5adac41e33de")
SWAP_BASE_OUTPUT_DISCRIMINATOR = bytes.fromhex("37d96256a34ab4ad")
WITHDRAW_DISCRIMINATOR = bytes.fromhex("b712469c946da122")

LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_DECIMALS = 9
TOKEN_WITH_DECIMALS = 10 ** TOKEN_DECIMALS
MILLION = 10 ** 6

AMM_CONFIG_INDEX = 0

RPC_WS_URL = "wss://lb.drpc.org/ogws?network=solana&dkey=Anel9UV-y0b6gj9ghgRejMrjRyztV4IR8JXsrqRhf0fE"
RPC_HTTP_URL = "https://lb.drpc.org/solana/Anel9UV-y0b6gj9ghgRejMrjRyztV4IR8JXsrqRhf0fE"

HELIUS_HTTPS = "https://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2"
HELIUS_WSS = "wss://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2"
