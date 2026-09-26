from app import dedupe


class FakeRedis:
    def __init__(self):
        self.store, self.commands = {}, 0

    def mget(self, keys):
        self.commands += 1
        return [self.store.get(k) for k in keys]

    def pipeline(self):
        outer = self

        class Pipe:
            def set(self, k, v, ex=None):
                outer.commands += 1
                outer.store[k] = v

            def execute(self):
                return None
        return Pipe()


def it(url, title):
    return {"url": url, "title": title}


def test_only_unseen_items_pass_and_are_remembered(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(dedupe, "r", fake)
    first = dedupe.filter_new("ai", [it("https://a.com/1", "One"), it("https://a.com/2", "Two")])
    assert len(first) == 2
    again = dedupe.filter_new("ai", [it("https://a.com/1?utm=x", "One"), it("https://a.com/3", "Three")])
    assert [i["title"] for i in again] == ["Three"]


def test_repeats_inside_one_run_count_once(monkeypatch):
    monkeypatch.setattr(dedupe, "r", FakeRedis())
    out = dedupe.filter_new("ai", [it("https://a.com/1", "Same"), it("https://www.a.com/1/", "Other title")])
    assert len(out) == 1


def test_a_run_costs_one_lookup_plus_one_write_per_new_key(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(dedupe, "r", fake)
    dedupe.filter_new("ai", [it(f"https://a.com/{n}", f"T{n}") for n in range(50)])
    fake.commands = 0
    dedupe.filter_new("ai", [it(f"https://a.com/{n}", f"T{n}") for n in range(50)])
    assert fake.commands == 1


def test_nothing_in_nothing_out(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(dedupe, "r", fake)
    assert dedupe.filter_new("ai", []) == [] and fake.commands == 0
