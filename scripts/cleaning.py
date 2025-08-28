from pathlib import Path
from typing import List, Dict, Tuple
import base58
from solders.instruction import AccountMeta, Instruction
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.message import Message
from solders.hash import Hash
from spl.token.instructions import (
    burn_checked, BurnCheckedParams,
    close_account, CloseAccountParams,
)
from spl.token.constants import TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID

TOKEN_PROGRAM_2022_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2"
PRIVATE_KEYS_FILE = Path(__file__).parent / "private_keys.txt"
FEE_PAYER_BASE58 = "3KJRU2Q8ps4P8X2u7S1vVK4Vz1bgz8YdF5n4AxaYbrRPDNb8C18Jmh4cGcMyVquRQqxF3MNYaHcnEUZiDysNUAZ8"

MAX_INSTRUCTIONS_PER_TX = 10
TOKEN_ACCOUNT_RENT = 2039280

client = Client(RPC_URL)
FEE_PAYER = Keypair.from_bytes(base58.b58decode(FEE_PAYER_BASE58))

JSON_FORMAT = True

def load_wallets(path: str, json: bool = False) -> List[Keypair]:
    wallets = []

    with open(path, "r") as f:
        for line in f:
            key_str = line.strip().strip(',').strip('"').strip("'")  # Удаляем запятые и кавычки
            if not key_str:
                continue
            try:
                sk = base58.b58decode(key_str)
                wallets.append(Keypair.from_bytes(sk))
            except Exception as e:
                print(f"[!] Invalid line: {line.strip()} → {e}")
    return wallets

def get_token_accounts(owner: Pubkey) -> List:
    accounts = []
    for program in [TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID]:
        resp = client.get_token_accounts_by_owner_json_parsed(
            owner,
            TokenAccountOpts(
                encoding="jsonParsed",
                program_id=program,
            )
        )
        accounts += resp.value
    return accounts

def parse_accounts(wallet: Keypair) -> List[Dict]:
    result = []
    accounts = get_token_accounts(wallet.pubkey())
    for acc in accounts:
        try:
            parsed = acc.account.data.parsed["info"]
            mint = Pubkey.from_string(parsed["mint"])
            amount = int(parsed["tokenAmount"]["amount"])
            decimals = int(parsed["tokenAmount"]["decimals"])
            program = acc.account.owner

            withheld_amt = 0

            if program == TOKEN_2022_PROGRAM_ID:
                extensions = parsed.get("extensions", [])
                for ext in extensions:
                    if ext.get("extension") == "transferFeeAmount":
                        state = ext.get("state", {})
                        withheld_amt = int(state.get("withheldAmount", 0))
                        break

            withheld = False
            if withheld_amt > 0:
                withheld = True

            result.append({
                "token_account": acc.pubkey,
                "mint": mint,
                "amount": amount,
                "owner": wallet,
                "decimals": decimals,
                "program_id": program,
                "withheld": withheld
            })
        except Exception as e:
            print(f"[!] Parse error: {e}")
    return result

HARVEST_WITHHELD_DISCRIMINATOR = bytes((26, 4))

def ix_harvest_withheld_tokens_to_mint(
    mint: Pubkey,
    source_token_accounts: list[Pubkey],
) -> Instruction:
    # bytes layout: [discriminator=26, transferFeeDiscriminator=4]
    data = HARVEST_WITHHELD_DISCRIMINATOR

    accounts = [
        AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
    ]
    accounts += [
        AccountMeta(pubkey=acc, is_signer=False, is_writable=True)
        for acc in source_token_accounts
    ]

    return Instruction(
        program_id=TOKEN_PROGRAM_2022_ID,
        accounts=accounts,
        data=data,
    )

def build_instructions(entry: Dict, receiver: Pubkey) -> List[Instruction]:
    program_id = entry["program_id"]
    account = entry["token_account"]
    mint = entry["mint"]
    amount = entry["amount"]
    owner = entry["owner"]
    withheld = entry["withheld"]

    ixs = []

    try:
        if withheld:
            ixs.append(
                ix_harvest_withheld_tokens_to_mint(
                    mint=mint,
                    source_token_accounts=[account]
                )
            )

        if amount > 0:
            ixs.append(burn_checked(
                BurnCheckedParams(
                    program_id=program_id,
                    account=account,
                    mint=mint,
                    owner=owner.pubkey(),
                    amount=amount,
                    decimals=entry["decimals"],
                    signers=[]
                )
            ))

        ixs.append(close_account(
            CloseAccountParams(
                program_id=program_id,
                account=account,
                owner=owner.pubkey(),
                dest=receiver
            )
        ))
        return ixs
    except Exception as e:
        print(f"[!] Failed to build instructions for {mint}: {e}")
        return []


def send_tx(ixs: List[Instruction], signers: List[Keypair], fee_payer: Keypair) -> Tuple[int, int]:
    try:
        resp = client.get_latest_blockhash()
        blockhash = resp.value.blockhash
        msg = Message(ixs, fee_payer.pubkey())
        tx = Transaction([fee_payer, *signers], msg, blockhash)
        sig = client.send_transaction(tx)
        print(f"✅ TX sent: {sig}")
        closed_accounts = len([ix for ix in ixs if ix.data[0] == 9])  # CloseAccount opcode = 9
        return closed_accounts, closed_accounts * TOKEN_ACCOUNT_RENT
    except Exception as e:
        print(f"❌ TX failed: {e}")
        return 0, 0

def est_size(payer: Pubkey, ixs: list[Instruction], signer_cnt: int) -> int:
    msg = Message.new_with_blockhash(ixs, payer, Hash.default())
    return len(bytes(msg)) + 1 + 64 * max(1, signer_cnt)

def send_batches(instructions_with_signers: List[Tuple[List[Instruction], Keypair]], fee_payer: Keypair) -> Tuple[int, int]:
    batch: List[Instruction] = []
    signer_map: Dict[str, Keypair] = {}
    closed_accounts = 0
    total_lamports = 0

    for instrs, signer in instructions_with_signers:
        if not instrs:
            continue
        batch.extend(instrs)
        signer_map[str(signer.pubkey())] = signer
        if est_size(FEE_PAYER.pubkey(), batch ,len(signer_map.keys())) >= 1000:
            ca, lam = send_tx(batch, list(signer_map.values()), fee_payer)
            closed_accounts += ca
            total_lamports += lam
            batch = []
            signer_map = {}
    if batch:
        ca, lam = send_tx(batch, list(signer_map.values()), fee_payer)
        closed_accounts += ca
        total_lamports += lam

    return closed_accounts, total_lamports


def main():
    wallets = load_wallets(PRIVATE_KEYS_FILE)
    all_entries = []
    for wallet in wallets:
        parsed = parse_accounts(wallet)
        print(f"[+] {wallet.pubkey()} — {len(parsed)} token accounts")
        all_entries.extend(parsed)

    print(f"\n[INFO] Total accounts to process: {len(all_entries)}")
    instructions = []
    for acc in all_entries:
        ix = build_instructions(acc, FEE_PAYER.pubkey())
        if ix:
            print(f"Prepared burn+close for mint: {acc['mint']}")
            instructions.append((ix, acc["owner"]))

    closed, lamports = send_batches(instructions, FEE_PAYER)

    print("\n=== 📊 REPORT ===")
    print(f"✅ Closed accounts: {closed}")
    print(f"💰 Estimated SOL earned: {lamports / 1e9:.6f} SOL")


if __name__ == "__main__":
    main()
