"""Supported chains and their ids on each free API. Add a chain = add one line.

`security` says which free safety API can vet a token there:
  "rugcheck" / "goplus" -> the token_scout can run the full course checklist.
  None                  -> LOOKUP ONLY: search, price, journal, watchlist and guardian alerts
                           all work, but there is no free safety report, and the checklist's
                           fail-safe rule means the scout must not pretend otherwise.
`gecko` may be None when GeckoTerminal does not carry the chain (no candles, no discovery).
All ids below were read from the live GoPlus, DexScreener and GeckoTerminal APIs."""
import re


def _c(gecko, dex, goplus=None, security=None):
    return {"gecko": gecko, "dex": dex, "goplus": goplus, "security": security}


CHAINS = {
    # ---- full safety report available: the scout can run the checklist here ----
    "solana":     _c("solana", "solana", None, "rugcheck"),
    "ethereum":   _c("eth", "ethereum", "1", "goplus"),
    "base":       _c("base", "base", "8453", "goplus"),
    "bsc":        _c("bsc", "bsc", "56", "goplus"),
    "arbitrum":   _c("arbitrum", "arbitrum", "42161", "goplus"),
    "polygon":    _c("polygon_pos", "polygon", "137", "goplus"),
    "avalanche":  _c("avax", "avalanche", "43114", "goplus"),
    "optimism":   _c("optimism", "optimism", "10", "goplus"),
    "tron":       _c("tron", "tron", "tron", "goplus"),
    "blast":      _c("blast", "blast", "81457", "goplus"),
    "linea":      _c("linea", "linea", "59144", "goplus"),
    "scroll":     _c("scroll", "scroll", "534352", "goplus"),
    "zksync":     _c("zksync", "zksync", "324", "goplus"),
    "mantle":     _c("mantle", "mantle", "5000", "goplus"),
    "cronos":     _c("cro", "cronos", "25", "goplus"),
    "opbnb":      _c("opbnb", "opbnb", "204", "goplus"),
    "sonic":      _c("sonic", "sonic", "146", "goplus"),
    "berachain":  _c("berachain", "berachain", "80094", "goplus"),
    "unichain":   _c("unichain", "unichain", "130", "goplus"),
    "worldchain": _c("world-chain", "worldchain", "480", "goplus"),
    "abstract":   _c("abstract", "abstract", "2741", "goplus"),
    "soneium":    _c("soneium", "soneium", "1868", "goplus"),
    "monad":      _c("monad", "monad", "143", "goplus"),
    "manta":      _c("manta-pacific", "manta", "169", "goplus"),
    # ---- lookup only: no free safety API yet, so the scout stays away ----
    "ton":        _c("ton", "ton"),
    "sui":        _c("sui-network", "sui"),
    "aptos":      _c("aptos", "aptos"),
    "near":       _c("near", "near"),
    "sei":        _c("sei-evm", "seiv2"),
    "hyperevm":   _c("hyperevm", "hyperevm"),
    "starknet":   _c("starknet-alpha", "starknet"),
    "injective":  _c("injective", "injective"),
    "xrpl":       _c("xrpl", "xrpl"),
    "celo":       _c("celo", "celo"),
    "pulsechain": _c("pulsechain", "pulsechain"),
    "ink":        _c("ink", "ink"),
    "hedera":     _c("hedera-hashgraph", "hedera"),
    "algorand":   _c(None, "algorand"),
}
DEX_TO_CHAIN = {v["dex"]: k for k, v in CHAINS.items()}
GECKO_TO_CHAIN = {v["gecko"]: k for k, v in CHAINS.items() if v["gecko"]}
# Chains the token_scout may deep-check: a checklist without a safety report is not a checklist.
SCOUT_CHAINS = [name for name, v in CHAINS.items() if v["security"]]
LOOKUP_ONLY = [name for name, v in CHAINS.items() if not v["security"]]

# Address shapes, longest and most specific first. Chains disagree wildly - EVM hex, Solana and
# Tron base58, TON base64url, Sui/Aptos Move types - so anything not listed here falls through to
# a plain DexScreener search, which accepts an address as a query too.
_SHAPES = [
    r"0x[0-9a-fA-F]{1,64}::[A-Za-z0-9_]+::[A-Za-z0-9_]+",   # aptos / sui move type
    r"0x[0-9a-fA-F]{60,64}",                                # sui object, starknet
    r"0x[0-9a-fA-F]{40}",                                   # evm
    r"0:[0-9a-fA-F]{64}",                                   # ton, raw form
    r"[A-Za-z0-9_-]{48}",                                   # ton, user-friendly form
    r"[1-9A-HJ-NP-Za-km-z]{32,44}",                         # solana, tron
]
_ADDRESS = re.compile("|".join(f"(?<![0-9A-Za-z_:-])(?:{shape})(?![0-9A-Za-z_-])" for shape in _SHAPES))
_PURE_HEX = re.compile(r"^0x[0-9a-fA-F]+$")


def find_address(text: str) -> str | None:
    """First thing in `text` that looks like a token address on any supported chain."""
    match = _ADDRESS.search(text or "")
    return match.group(0) if match else None


def is_address(text: str) -> bool:
    text = (text or "").strip()
    match = _ADDRESS.fullmatch(text)
    return bool(match)


def norm(chain: str, address: str) -> str:
    """Plain hex addresses are case-insensitive; base58, base64url and Move types are NOT,
    so only lowercase what is safe to lowercase."""
    return address.lower() if _PURE_HEX.match(address or "") else address


def coin_key(chain: str, address: str) -> str:
    return f"{chain}:{norm(chain, address)}"


def has_security(chain: str) -> bool:
    return bool((CHAINS.get(chain) or {}).get("security"))
