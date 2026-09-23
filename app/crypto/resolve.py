"""Turn anything the user types into a token: a name ("bonk"), a pasted URL, or a raw address.

The user never has to find or copy a contract address - this module does it for them.
Read-only: it only ever reads public market data."""
from dataclasses import dataclass
from urllib.parse import urlparse

from . import dexscreener as dx
from .chains import CHAINS, DEX_TO_CHAIN, find_address, norm

# Host (or host fragment) -> our chain name, for links people actually paste.
HOST_CHAIN = {
    "pump.fun": "solana", "solscan.io": "solana", "birdeye.so": "solana", "jup.ag": "solana",
    "etherscan.io": "ethereum", "basescan.org": "base", "bscscan.com": "bsc", "arbiscan.io": "arbitrum",
    "polygonscan.com": "polygon", "snowtrace.io": "avalanche", "snowscan.xyz": "avalanche",
    "optimistic.etherscan.io": "optimism", "lineascan.build": "linea", "blastscan.io": "blast",
    "scrollscan.com": "scroll", "mantlescan.xyz": "mantle", "cronoscan.com": "cronos",
    "opbnbscan.com": "opbnb", "sonicscan.org": "sonic", "berascan.com": "berachain",
    "uniscan.xyz": "unichain", "worldscan.org": "worldchain", "abscan.org": "abstract",
    "soneium.blockscout.com": "soneium", "monadexplorer.com": "monad", "pacific-explorer.manta.network": "manta",
    "tronscan.org": "tron", "tronscan.io": "tron",
    "tonviewer.com": "ton", "tonscan.org": "ton", "ton.app": "ton", "dedust.io": "ton", "ston.fi": "ton",
    "suiscan.xyz": "sui", "suivision.xyz": "sui", "aptoscan.com": "aptos", "explorer.aptoslabs.com": "aptos",
    "nearblocks.io": "near", "seitrace.com": "sei", "hyperevmscan.io": "hyperevm",
    "starkscan.co": "starknet", "voyager.online": "starknet", "explorer.injective.network": "injective",
    "xrpscan.com": "xrpl", "celoscan.io": "celo", "otterscan.pulsechain.com": "pulsechain",
    "explorer.inkonchain.com": "ink", "hashscan.io": "hedera", "allo.info": "algorand",
}
# DexScreener / GeckoTerminal put the chain in the path: dexscreener.com/<chain>/<pool>
PATH_CHAIN = {**{v["dex"]: k for k, v in CHAINS.items()}, **{v["gecko"]: k for k, v in CHAINS.items()}}
MAX_CANDIDATES = 5


@dataclass
class Candidate:
    """One tappable search result. `address` is kept internally; the user never sees it."""
    chain: str
    address: str
    symbol: str = ""
    name: str = ""
    price: float | None = None
    mcap: float | None = None
    liquidity: float | None = None
    vol24: float | None = None
    chg24: float | None = None
    age_hours: float | None = None
    has_socials: bool = False
    pair_url: str = ""
    pool: str = ""

    @property
    def key(self) -> str:
        return f"{self.chain}:{self.address}"


def extract_address(text: str) -> tuple[str | None, str | None]:
    """(chain_hint, address) from a URL or loose text. Either may be None."""
    text = (text or "").strip()
    chain = None
    if "://" in text or text.lower().startswith("www."):
        url = text if "://" in text else "https://" + text
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        for known, name in HOST_CHAIN.items():
            if host == known or host.endswith("." + known):
                chain = name
                break
        for part in parsed.path.split("/"):
            if part in PATH_CHAIN:
                chain = PATH_CHAIN[part]
                break
    address = find_address(text)
    if not address:
        return chain, None
    if chain in ("solana", "ton") and address.startswith("0x"):
        chain = None                        # an 0x address cannot be on those chains
    return chain, norm(chain or "", address)


def _same_address(a: str, b: str) -> bool:
    return (a or "").lower() == (b or "").lower()


def candidates_from_pairs(pairs: list[dict], address: str | None = None,
                          limit: int = MAX_CANDIDATES) -> list[Candidate]:
    """Best (highest-liquidity) pair per token, on supported chains only, richest first."""
    best: dict[str, dict] = {}
    for p in pairs:
        chain = DEX_TO_CHAIN.get(p.get("chainId"))
        base = (p.get("baseToken") or {}).get("address")
        if not chain or not base:
            continue
        if address and not (_same_address(base, address) or _same_address(p.get("pairAddress"), address)):
            continue
        key = f"{chain}:{norm(chain, base)}"
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if key not in best or liq > ((best[key].get("liquidity") or {}).get("usd") or 0):
            best[key] = p
    out = []
    for key, p in best.items():
        chain, addr = key.split(":", 1)
        b = dx.basics(p)
        out.append(Candidate(chain=chain, address=addr, symbol=b["symbol"], name=b["name"],
                             price=b["price"], mcap=b["mcap"], liquidity=b["liquidity"],
                             vol24=b["vol24"], chg24=b["chg24"], age_hours=b["age_hours"],
                             has_socials=bool(b["twitter"] or b["telegram"] or b["websites"]),
                             pair_url=b["pair_url"], pool=b["pool"]))
    out.sort(key=lambda c: -(c.liquidity or 0))
    return out[:limit]


async def resolve(c, query: str, limit: int = MAX_CANDIDATES) -> list[Candidate]:
    """Name, ticker, URL or address -> ranked candidates. Empty list = nothing found."""
    chain_hint, address = extract_address(query)
    term = address or (query or "").strip()
    if not term:
        return []
    try:
        pairs = await dx.search(c, term)
    except Exception:
        pairs = []
    found = candidates_from_pairs(pairs, address, limit)
    if found or not address:
        return found
    # A pasted URL usually carries a POOL address, which search may not match.
    for chain in ([chain_hint] if chain_hint else list(CHAINS)):
        try:
            p = await dx.pair(c, chain, address)
        except Exception:
            p = None
        if p:
            return candidates_from_pairs([p], None, limit)
    return []


async def one(c, chain: str, address: str) -> Candidate | None:
    """The single token behind a "<chain>:<address>" key, with its live market data."""
    if chain not in CHAINS:
        return None
    try:
        pairs = await dx.pairs_for(c, chain, [norm(chain, address)])
    except Exception:
        return None
    found = candidates_from_pairs(pairs, address, limit=1)
    return found[0] if found else None
