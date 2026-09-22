Topic: {label}
Item: "{title}"  ({url})

Use web search. Confirm ONLY from the project's own channels (official site, docs, blog, verified X account).
Return ONLY a JSON object:
{{"official_site": "<official homepage or null>",
 "action_link": "<claim / eligibility-checker URL on the OFFICIAL domain, or null>",
 "what_to_do": "<the single next step, one wallet only>",
 "cost": "<free / gas only / other>",
 "deadline": "<claim or snapshot deadline, or null>",
 "india_availability": "<available / geo-blocked / KYC-required / unknown>",
 "legitimacy": "<confirmed | unconfirmed | suspicious>",
 "evidence": "<which official source confirmed it>",
 "red_flags": ["<e.g. asks for seed phrase, requires sending funds, lookalike domain, link only in replies/DMs>"]}}
If the project has not officially announced it, legitimacy is "unconfirmed". Never invent links.
Never suggest using multiple wallets.
