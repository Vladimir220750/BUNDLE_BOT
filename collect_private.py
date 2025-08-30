import os

INPUT_DIR = "./app/wallets"
OUTPUT_FILE = "all_keys.txt"

def main():
    keys = []
    for fname in os.listdir(INPUT_DIR):
        fpath = os.path.join(INPUT_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                keys.append(key)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write(",\n".join(keys))

    print(f"Собрано {len(keys)} ключей → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()