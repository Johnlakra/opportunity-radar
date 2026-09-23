import pytest

from app.crypto.chains import (CHAINS, DEX_TO_CHAIN, LOOKUP_ONLY, SCOUT_CHAINS, coin_key,
                               find_address, has_security, is_address, norm)

# One real address per address shape the supported chains actually use.
ADDRESSES = {
    "solana": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "tron": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "ton": "EQA2kCVNwVsil2EM2mB0SkXytxCqQjS4mttjDpnXmwG9T6bO",
    "sui": "0x0000000000000000000000000000000000000000000000000000000000000002::sui::SUI",
    "aptos": "0x1::aptos_coin::AptosCoin",
    "starknet": "0x05574eb6b8789a91466f902c380d978e472db68170ff82a5b650b95a58ddf4ad",
}


@pytest.mark.parametrize("chain,address", sorted(ADDRESSES.items()))
def test_every_supported_address_shape_is_recognised(chain, address):
    assert is_address(address)
    assert find_address(f"look at {address} please") == address


def test_junk_is_not_an_address():
    assert not is_address("bonk") and not is_address("") and not is_address("send me $50")


def test_hex_addresses_are_lowercased_because_they_are_case_insensitive():
    assert norm("ethereum", "0xA0B8") == "0xa0b8"


def test_case_sensitive_addresses_are_left_alone():
    assert norm("solana", ADDRESSES["solana"]) == ADDRESSES["solana"]
    assert norm("ton", ADDRESSES["ton"]) == ADDRESSES["ton"]
    assert norm("tron", ADDRESSES["tron"]) == ADDRESSES["tron"]


def test_move_types_must_not_be_lowercased():
    # lowercasing "AptosCoin" would point at a token that does not exist
    assert norm("aptos", ADDRESSES["aptos"]) == "0x1::aptos_coin::AptosCoin"
    assert norm("sui", ADDRESSES["sui"]).endswith("::sui::SUI")


def test_coin_key_round_trips_a_ton_address():
    key = coin_key("ton", ADDRESSES["ton"])
    chain, _, address = key.partition(":")
    assert chain == "ton" and address == ADDRESSES["ton"]


def test_the_original_five_chains_are_still_there():
    for chain in ("solana", "ethereum", "base", "bsc", "arbitrum"):
        assert chain in CHAINS and has_security(chain)


def test_ton_and_friends_are_lookup_only():
    for chain in ("ton", "sui", "aptos", "near"):
        assert chain in CHAINS and not has_security(chain)
        assert chain in LOOKUP_ONLY and chain not in SCOUT_CHAINS


def test_scout_chains_all_have_a_safety_source():
    assert SCOUT_CHAINS and all(has_security(chain) for chain in SCOUT_CHAINS)
    assert set(SCOUT_CHAINS) | set(LOOKUP_ONLY) == set(CHAINS)


def test_goplus_chains_carry_an_id_and_rugcheck_chains_do_not_need_one():
    for name, cfg in CHAINS.items():
        if cfg["security"] == "goplus":
            assert cfg["goplus"], f"{name} has no GoPlus chain id"
        if cfg["security"] == "rugcheck":
            assert name == "solana"


def test_dex_ids_are_unique_so_a_pair_maps_back_to_one_chain():
    assert len(DEX_TO_CHAIN) == len(CHAINS)
