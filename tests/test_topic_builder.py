import yaml

from app import topic_builder as tb


def sandbox(tmp_path):
    root = tmp_path / "topics"
    root.mkdir()
    config = tmp_path / "agents.yaml"
    config.write_text("agents:\n  news_ai:\n    type: news\n    topic: ai\n", encoding="utf-8")
    return root, config


def test_a_slug_is_made_from_whatever_you_typed():
    assert tb.slugify("Hackathons!") == "hackathons"
    assert tb.slugify("Dev Grants") == "dev_grants"


def test_only_safe_names_are_accepted(tmp_path):
    root, _ = sandbox(tmp_path)
    assert tb.validate("hackathons", root)[0]
    for bad in ("../etc", "Hack Athons", "", "a", "x" * 31, "token_scout"):
        assert not tb.validate(bad, root)[0]


def test_an_existing_topic_is_not_overwritten(tmp_path):
    root, _ = sandbox(tmp_path)
    (root / "grants").mkdir()
    assert not tb.validate("grants", root)[0]


def test_creating_a_topic_writes_all_three_pieces(tmp_path):
    root, config = sandbox(tmp_path)
    ok, label = tb.create_topic("hackathons", ["hackathon india apply"], root, config)
    assert ok and label == "Hackathons"
    assert (root / "hackathons" / "profile.md").exists()
    sources = yaml.safe_load((root / "hackathons" / "sources.yaml").read_text())
    assert sources["google_news"][0]["q"] == "hackathon india apply"
    agents = yaml.safe_load(config.read_text())["agents"]
    assert agents["news_hackathons"]["topic"] == "hackathons"
    assert agents["news_ai"]["topic"] == "ai"          # the existing entries survive


def test_the_profile_always_carries_the_safety_line(tmp_path):
    root, config = sandbox(tmp_path)
    tb.create_topic("grants", [], root, config)
    assert "seed phrase" in (root / "grants" / "profile.md").read_text()


def test_queries_are_cleaned_and_capped():
    assert tb.clean_queries([" a  b ", "a b", "", None] + [f"q{i}" for i in range(9)])[0] == "a b"
    assert len(tb.clean_queries([f"q{i}" for i in range(9)])) == tb.MAX_QUERIES


def test_a_label_with_a_quote_cannot_break_the_config(tmp_path):
    root, config = sandbox(tmp_path)
    entry = tb.agent_entry("x", 'evil": {a: b}')
    assert yaml.safe_load("agents:\n" + entry)["agents"]["news_x"]["label"] == 'evil": {a: b}'


def test_empty_queries_fall_back_to_sensible_defaults(tmp_path):
    root, config = sandbox(tmp_path)
    tb.create_topic("grants", [], root, config)
    sources = yaml.safe_load((root / "grants" / "sources.yaml").read_text())
    assert len(sources["google_news"]) == len(tb.suggest_queries("grants"))
