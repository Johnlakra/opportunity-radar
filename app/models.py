from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def now():
    return datetime.now(timezone.utc)


class Item(SQLModel, table=True):
    """A news-style item from any news topic (ai, crypto_news, airdrops, listings...)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    url: str
    title: str
    source: str = ""
    summary: str = ""
    fetched_at: datetime = Field(default_factory=now)
    score: Optional[int] = None
    category: Optional[str] = None
    action: Optional[str] = None
    urgency: Optional[str] = None
    why: Optional[str] = None
    personal: bool = False           # touches your holdings / exchanges / chains
    researched: bool = False
    research_json: Optional[str] = None
    action_link: Optional[str] = None
    flagged: bool = False            # research found red flags -> never delivered


class Alert(SQLModel, table=True):
    """Every candidate message from every topic. The cream gate decides which get sent."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)   # dedupe key, e.g. "news:123", "tp:eth:0xabc:5"
    topic: str = Field(index=True)
    priority: int                               # 0-100
    text: str
    buttons_json: str = "[]"
    created_at: datetime = Field(default_factory=now)
    sent_mode: str = ""                         # "" queued | urgent | digest | dropped


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    ref: str
    title: str
    category: Optional[str] = None
    vote: str  # "up" | "down"
    created_at: datetime = Field(default_factory=now)


class Coin(SQLModel, table=True):
    """A DEX token (any supported chain) the scout has deep-checked."""
    key: str = Field(primary_key=True)          # "<chain>:<address>"
    chain: str = Field(index=True)
    address: str
    symbol: str = ""
    name: str = ""
    pair_url: str = ""
    stage: str = "WATCH"                        # REJECT | WATCH | BUY_ZONE
    user_status: str = ""                       # "" | watch | ignore
    score: int = 0
    mcap: Optional[float] = None
    reasons_json: str = "{}"
    first_seen: datetime = Field(default_factory=now)
    last_checked: datetime = Field(default_factory=now)


class Holding(SQLModel, table=True):
    """Your journal (the course's spreadsheet, in the DB).
    kind="cg"  -> CoinGecko id (BTC, ETH, SOL, any listed coin); entry = price
    kind="dex" -> "<chain>:<address>" DEX token; entry = market cap"""
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str
    ref: str = Field(index=True)
    symbol: str = ""
    entry_value: float
    usd: float
    added_at: datetime = Field(default_factory=now)
