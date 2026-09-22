"""Supported chains and their ids on each free API. Add a chain = add one line."""
CHAINS = {
    "solana":   {"gecko": "solana",   "dex": "solana",   "goplus": None},    # security via RugCheck
    "ethereum": {"gecko": "eth",      "dex": "ethereum", "goplus": "1"},
    "base":     {"gecko": "base",     "dex": "base",     "goplus": "8453"},
    "bsc":      {"gecko": "bsc",      "dex": "bsc",      "goplus": "56"},
    "arbitrum": {"gecko": "arbitrum", "dex": "arbitrum", "goplus": "42161"},
}
DEX_TO_CHAIN = {v["dex"]: k for k, v in CHAINS.items()}
GECKO_TO_CHAIN = {v["gecko"]: k for k, v in CHAINS.items()}


def norm(chain: str, address: str) -> str:
    """EVM addresses are case-insensitive; Solana (base58) is case-sensitive."""
    return address if chain == "solana" else address.lower()


def coin_key(chain: str, address: str) -> str:
    return f"{chain}:{norm(chain, address)}"
