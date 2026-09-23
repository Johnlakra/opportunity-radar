from app.crypto.resolve import Candidate, candidates_from_pairs, extract_address

SOL_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def pair(chain="solana", addr=SOL_MINT, liq=10_000, symbol="BONK", socials=True):
    return {"chainId": chain, "pairAddress": "POOL" + symbol, "url": "https://dexscreener.com/x",
            "baseToken": {"address": addr, "symbol": symbol, "name": symbol + " Coin"},
            "liquidity": {"usd": liq}, "marketCap": 120_000, "fdv": 120_000,
            "volume": {"h24": 9000}, "priceChange": {"h24": -5}, "pairCreatedAt": 1,
            "info": {"socials": [{"type": "twitter", "url": "https://x.com/a"}]} if socials else {}}


def test_plain_name_has_no_address():
    assert extract_address("bonk") == (None, None)


def test_reads_mint_out_of_a_pump_fun_link():
    assert extract_address(f"https://pump.fun/coin/{SOL_MINT}") == ("solana", SOL_MINT)


def test_reads_chain_and_address_out_of_an_explorer_link():
    assert extract_address(f"https://etherscan.io/token/{USDC}") == ("ethereum", USDC.lower())


def test_dexscreener_link_gives_the_chain_from_the_path():
    chain, addr = extract_address(f"https://dexscreener.com/base/{USDC}")
    assert (chain, addr) == ("base", USDC.lower())


def test_evm_address_is_never_read_as_base58():
    assert extract_address(f"my bag is {USDC}") == (None, USDC.lower())


TON_MINT = "EQA2kCVNwVsil2EM2mB0SkXytxCqQjS4mttjDpnXmwG9T6bO"


def test_reads_a_ton_address_out_of_a_tonviewer_link():
    assert extract_address(f"https://tonviewer.com/{TON_MINT}") == ("ton", TON_MINT)


def test_reads_a_tron_address_out_of_a_tronscan_link():
    tron = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    assert extract_address(f"https://tronscan.org/#/token20/{tron}") == ("tron", tron)


def test_reads_a_sui_move_type_without_mangling_its_case():
    sui = "0x2::sui::SUI"
    assert extract_address(f"https://suiscan.xyz/mainnet/coin/{sui}") == ("sui", sui)


def test_dexscreener_ton_link_gives_the_ton_chain():
    assert extract_address(f"https://dexscreener.com/ton/{TON_MINT}") == ("ton", TON_MINT)


def test_address_is_found_inside_a_forwarded_message():
    assert extract_address(f"ape this {SOL_MINT} now")[1] == SOL_MINT


def test_candidates_keep_the_deepest_pool_per_token_and_rank_by_liquidity():
    found = candidates_from_pairs([pair(liq=1_000, symbol="A"), pair(liq=90_000, symbol="A"),
                                   pair(chain="base", addr=USDC, liq=50_000, symbol="B")])
    assert [c.symbol for c in found] == ["A", "B"]
    assert found[0].liquidity == 90_000 and found[0].chain == "solana"


def test_unsupported_chains_are_dropped():
    assert candidates_from_pairs([pair(chain="cardano")]) == []


def test_address_filter_keeps_only_that_token():
    found = candidates_from_pairs([pair(symbol="A"), pair(chain="base", addr=USDC, symbol="B")], address=USDC)
    assert [c.symbol for c in found] == ["B"]


def test_a_pool_address_also_matches():
    assert candidates_from_pairs([pair(symbol="A")], address="POOLA")[0].symbol == "A"


def test_socials_flag_drives_the_tick():
    assert candidates_from_pairs([pair(socials=True)])[0].has_socials
    assert not candidates_from_pairs([pair(socials=False)])[0].has_socials


def test_key_is_chain_and_address():
    assert Candidate(chain="solana", address=SOL_MINT).key == f"solana:{SOL_MINT}"
