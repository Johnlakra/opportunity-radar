"""Plain-English glossary. Every jargon word in a card gets a "What does this mean?" button."""
TERMS = {
    "mcap": ("Market cap",
             "The value of every coin that exists, added up. A $100k coin is tiny; a $1B coin is huge. "
             "Small coins can move a lot, and can also go to zero."),
    "liq": ("Liquidity",
            "The money sitting in the pool you trade against. Low liquidity means your sell can move "
            "the price against you. The course likes liquidity smaller than market cap, but not tiny."),
    "lp": ("LP locked / burned",
           "The pool money is locked away (or destroyed) so the team cannot pull it out and run. "
           "Under 90% locked is a red flag."),
    "auth": ("Mint & freeze authority",
             "Switches that let a team print new coins or freeze yours. Renounced means the switches "
             "are gone forever - that is what you want."),
    "holders": ("Holders",
                "How many wallets own the coin. A few hundred is a small circle; several thousand "
                "means a real crowd."),
    "whale": ("Top wallet %",
              "How much one private wallet owns. Above 10% means one person can dump on you. "
              "Pool and exchange wallets do not count."),
    "fdv": ("FDV",
            "What the market cap becomes once every planned coin exists. Much bigger than market cap "
            "means a lot of hidden supply is still coming."),
    "range": ("Range position",
              "Where today's price sits between the recent low (0%) and recent high (100%). "
              "The course buys near the bottom, not the top."),
    "dd": ("Below ATH",
           "How far the coin is under its all-time high. Deeply down means the launch hype is over."),
    "dom": ("BTC dominance",
            "Bitcoin's share of all crypto value. Falling dominance while Bitcoin holds up is the "
            "classic sign money is rotating into smaller coins."),
    "fng": ("Fear & Greed",
            "A 0-100 mood gauge. Low means everyone is scared (historically better to buy); "
            "high means everyone is excited (historically worse)."),
    "regime": ("Market mood",
               "Which part of the cycle Bitcoin looks to be in, from its own price history: still "
               "falling, quietly ranging, or running up. It decides whether the course buys at all."),
    "honeypot": ("Honeypot",
                 "A coin you can buy but cannot sell. The safety check refuses anything that looks "
                 "like one."),
    "cto": ("CTO",
            "Community takeover - the original team left and volunteers took over. The course treats "
            "these as lower priority."),
    "picky": ("How picky",
              "The score an item must reach before I look into it. Strict means fewer, better "
              "items; relaxed means more of them. You can set it per topic."),
    "ping": ("Instant ping",
             "A message that interrupts you straight away instead of waiting for the daily "
             "summary. You choose how many of those I am allowed per day."),
    "quiet": ("Quiet hours",
              "Hours when nothing is allowed to interrupt you. Anything that came up waits for "
              "the daily summary. Alerts about coins you hold still come through."),
    "digest": ("Daily summary",
               "One message each morning with the best of everything the agents found, and "
               "nothing else. You pick the time."),
    "score": ("Score",
              "0 to 10, decided by the filter reading the item against your profile. Only the "
              "high ones are worth your attention, and only those get looked into further."),
    "cream": ("The cream gate",
              "Every agent sends its findings here. Only the highest-scoring few reach you: at most "
              "3 instant pings a day, the rest compete for the morning digest."),
}


def lookup(key: str) -> str | None:
    hit = TERMS.get(key)
    return f"<b>{hit[0]}</b>\n{hit[1]}" if hit else None


def index() -> str:
    lines = ["<b>❓ Glossary</b>", "Tap a word to see what it means in plain English.", ""]
    lines += [f"· <b>{title}</b>" for title, _ in TERMS.values()]
    return "\n".join(lines)
