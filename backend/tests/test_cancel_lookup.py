"""The cancel-page lookup: Tavily results checked against the merchant's own domains, cached per merchant, and
cancel steps read from the page only when each one is grounded in the page text. All with fake Tavily results."""

import json
from datetime import date, timedelta

import pytest

from clawback import config, rules
from clawback.models import Subscription
from clawback.pipeline import cancel_lookup
from clawback.pipeline.cancel import cancel_prep
from clawback.store import store
from clawback.tools import tavily

TODAY = date(2026, 10, 23)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
NETFLIX = Subscription(id="netflix", merchant="Netflix", category="video_streaming", monthly_cost=17.99)
HULU = Subscription(id="hulu", merchant="Hulu", category="video_streaming", monthly_cost=18.99)
GYM = Subscription(id="touchstone", merchant="Touchstone Climbing", category="unknown", monthly_cost=85.0)

NETFLIX_PAGE = """# How to cancel Netflix

If you no longer want Netflix, you can cancel your membership at any time.

1. Sign in to your [Account](https://www.netflix.com/account) page.
2. Select **Cancel Membership**.
3. Select **Finish Cancellation** to confirm.

Your account will stay open until the end of your billing period. If you were billed through a partner,
contact them to cancel. Questions about cancelling? Write to cancel-help@netflix.com.
Press inquiries: press@netflix.com."""


def result(url: str, title: str = "How to cancel", content: str = "Steps to cancel.") -> dict:
    return {"title": title, "url": url, "content": content}


class FakeTavily:
    def __init__(self, results: list[dict], pages: dict[str, str] | None = None, fail: bool = False) -> None:
        self.results, self.pages, self.fail = results, pages or {}, fail
        self.searches: list[tuple[str, dict]] = []
        self.extracts: list[list[str]] = []

    def search(self, user_id, stage, query, *, max_results=5, strict=False, **kwargs):
        self.searches.append((query, kwargs))
        if self.fail:
            if strict:
                raise tavily.SearchFailed("boom")
            return []
        return list(self.results)

    def extract(self, user_id, stage, urls):
        self.extracts.append(list(urls))
        return {u: self.pages[u] for u in urls if u in self.pages}


@pytest.fixture(autouse=True)
def fresh_user():
    store.reset("t")


@pytest.fixture()
def fake_tavily(monkeypatch):
    def install(results, pages=None, fail=False) -> FakeTavily:
        fake = FakeTavily(results, pages, fail)
        monkeypatch.setattr(tavily, "available", lambda: True)
        monkeypatch.setattr(tavily, "search", fake.search)
        monkeypatch.setattr(tavily, "extract", fake.extract)
        return fake
    return install


# --- The domain check ---------------------------------------------------------------------------------

@pytest.mark.parametrize("url, ok", [
    ("https://help.netflix.com/en/node/407", True),
    ("https://www.netflix.com/cancelplan", True),
    ("https://netflix.com/account", True),
    ("https://HELP.NETFLIX.COM./en/node/407", True),  # case and a trailing dot don't matter
    ("http://help.netflix.com/en/node/407", False),  # not https
    ("https://netflix-cancel.com/how-to", False),  # look-alike
    ("https://help.netflix.com.cancel-now.io/en", False),  # official name as a subdomain of someone else's site
    ("https://mynetflix.com/cancel", False),
    ("https://netflix.com@evil.example/cancel", False),  # user@host trick: the host is evil.example
    ("https://www.wikihow.com/Cancel-Netflix", False),
    ("https://community.netflix.com/t/cancel", False),  # user posts, even on the official domain
    ("https://help.netflix.com/thread/123", False),
    ("not a url", False),
    ("", False),
])
def test_on_domains(url, ok):
    assert rules.on_domains(url, ("netflix.com",)) is ok


def test_merchant_sites_data():
    rules.merchant_sites.cache_clear()
    data = rules.merchant_sites()
    names = [m.merchant for m in data.merchants]
    assert len(names) == len(set(names)) and "Netflix" in names
    for m in data.merchants:
        assert m.checked_on <= date.today()
        assert all(d == d.lower() and "." in d and "/" not in d and not d.startswith("www.") for d in m.domains), m
        assert m.owns(m.help_url), m  # each help centre is on the merchant's own domains
    assert rules.merchant_site("netflix").merchant == "Netflix"
    assert rules.merchant_site("DashPass").merchant == "DoorDash DashPass"  # by alias
    assert rules.merchant_site("Some Gym") is None
    # merchants.py names all have domains, from the data file or their sender domains
    from clawback.merchants import MERCHANTS
    assert all(cancel_lookup.official_domains(m.name) for m in MERCHANTS)


# --- The lookup ---------------------------------------------------------------------------------------

def test_official_page_is_verified_and_third_party_dropped(fake_tavily):
    fake = fake_tavily([result("https://www.wikihow.com/Cancel-Netflix", "How to Cancel Netflix: 5 Steps"),
                        result("https://help.netflix.com/en/node/407", "How to cancel Netflix | Netflix Help Center")])
    out = cancel_lookup.lookup("t", "Netflix", TODAY)
    assert fake.searches == [("Netflix help center: how to cancel your subscription",
                              {"include_domains": ["netflix.com"]})]
    assert out["links"] == [{"label": "How to cancel Netflix", "url": "https://help.netflix.com/en/node/407",
                             "verified": True}]
    assert out["verified"] is True and out["steps"] == []  # no model key: no steps read
    assert fake.extracts == []  # and no extract credit spent
    notes = [s.note for s in store.user("t").trace if s.engine == "code"]
    assert any("1 of 2 results on its own site (netflix.com); 1 other sites dropped" in n for n in notes)


def test_look_alikes_are_never_verified(fake_tavily):
    fake_tavily([result("https://netflix-cancel.com/how"), result("https://help.netflix.com.cancel-now.io/x"),
                 result("http://help.netflix.com/en/node/407"), result("https://netflix.com@evil.example/")])
    out = cancel_lookup.lookup("t", "Netflix", TODAY)
    assert out["links"] == [] and out["verified"] is False
    prep = cancel_prep("t", NETFLIX, TODAY)
    assert [l for l in prep["links"] if "netflix" in l["url"]] == []
    assert prep["steps"][0] == "Sign in on the merchant's website and look for Account > Subscription or Membership."


def test_unrelated_domains_and_community_posts_are_dropped(fake_tavily):
    fake_tavily([result("https://www.reddit.com/r/Hulu/comments/abc/cancel"),
                 result("https://community.hulu.com/s/question/cancel"),
                 result("https://www.cnet.com/tech/services-and-software/cancel-hulu/")])
    assert cancel_lookup.lookup("t", "Hulu", TODAY)["links"] == []


def test_no_results(fake_tavily):
    fake = fake_tavily([])
    out = cancel_lookup.lookup("t", "Hulu", TODAY)
    assert out["links"] == [] and out["verified"] is False and out["note"] is None
    assert [q for q, _ in fake.searches] == ["Hulu help center: how to cancel your subscription",
                                             "how to cancel Hulu"]  # one retry with a plainer query


def test_second_query_only_when_no_cancel_page_was_found(fake_tavily):
    fake = fake_tavily([result("https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus",
                               "What is ChatGPT Plus? | OpenAI Help Center", "About the plan."),
                        result("https://chatgpt.com/plans/plus", "ChatGPT Plan | Plus", "Plans.")])
    out = cancel_lookup.lookup("t", "ChatGPT Plus", TODAY)
    assert len(fake.searches) == 2  # the first answer had no page about cancelling
    # the best page is shown (verified, but labelled by its title); a second only when it is about cancelling
    assert out["links"] == [{"label": "What is ChatGPT Plus?", "verified": True,
                             "url": "https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus"}]


def test_ranking_prefers_a_general_cancel_page(fake_tavily):
    fake_tavily([result("https://www.adobe.com/creativecloud.html", "Creative Cloud | Adobe"),
                 result("https://helpx.adobe.com/stock/kb/cancel-membership-subscription-stock.html",
                        "Cancel your Adobe Stock membership | Stock"),  # another product: ranked lower
                 result("https://helpx.adobe.com/enterprise/cancel-team-plan.html", "Cancel an enterprise team plan"),
                 result("https://helpx.adobe.com/account/cancel-adobe-subscription.html",
                        "Cancel Adobe trial or subscription | Adobe Account"),
                 result("https://helpx.adobe.com/account/cancel-adobe-subscription.html?locale=en",
                        "Cancel Adobe trial or subscription | Adobe Account")])  # same page again: one link
    out = cancel_lookup.lookup("t", "Adobe Creative Cloud", TODAY)
    assert [l["url"] for l in out["links"]] == [
        "https://helpx.adobe.com/account/cancel-adobe-subscription.html",
        "https://helpx.adobe.com/stock/kb/cancel-membership-subscription-stock.html"]
    assert out["links"][0]["label"] == "Cancel Adobe trial or subscription"


def test_labels_never_carry_links(fake_tavily):
    fake_tavily([result("https://help.hulu.com/article/cancel-x", "Go to www.evil.example now | Hulu"),
                 result("https://help.hulu.com/article/manage", "Manage your plan")])  # not about cancelling
    labels = [l["label"] for l in cancel_lookup.lookup("t", "Hulu", TODAY)["links"]]
    assert labels == ["Hulu cancel page on help.hulu.com"]
    assert cancel_lookup._label("Hulu", result("https://help.hulu.com/a/1", "")) == "Hulu help page on help.hulu.com"


def test_unknown_merchant_shows_unverified_results(fake_tavily):
    fake = fake_tavily([result("https://touchstoneclimbing.com/membership"), result("https://www.yelp.com/biz/x"),
                        result("https://example.org/a"), result("http://insecure.example/b")])
    out = cancel_lookup.lookup("t", "Touchstone Climbing", TODAY)
    assert fake.searches[0][1] == {}  # no domains to limit the search to
    assert [(l["url"], l["verified"]) for l in out["links"]] == [
        ("https://touchstoneclimbing.com/membership", False), ("https://www.yelp.com/biz/x", False)]
    assert "not checked as Touchstone Climbing's own site" in out["links"][0]["label"]
    prep = cancel_prep("t", GYM, TODAY)
    assert prep["steps"][0].startswith("We couldn't confirm a cancel page on Touchstone Climbing's own site.")


def test_cache_per_merchant_with_a_date(fake_tavily):
    fake = fake_tavily([result("https://help.netflix.com/en/node/407")])
    cancel_lookup.lookup("t", "Netflix", TODAY)
    again = cancel_lookup.lookup("other-user", "netflix", TODAY + timedelta(days=30))  # shared across users
    assert again["from_cache"] is True and again["links"][0]["verified"] is True and len(fake.searches) == 1
    saved = json.loads(config.settings.cancel_cache_path.read_text(encoding="utf-8"))
    assert saved["merchants"]["netflix"]["checked_on"] == TODAY.isoformat()
    assert "from_cache" not in saved["merchants"]["netflix"]

    cancel_lookup.lookup("t", "Netflix", TODAY + timedelta(days=31))  # stale after 30 days: searched again
    assert len(fake.searches) == 2


def test_empty_answers_are_rechecked_sooner(fake_tavily):
    fake = fake_tavily([])
    cancel_lookup.lookup("t", "Hulu", TODAY)
    cancel_lookup.lookup("t", "Hulu", TODAY + timedelta(days=7))
    assert len(fake.searches) == 2  # both queries, once
    cancel_lookup.lookup("t", "Hulu", TODAY + timedelta(days=8))
    assert len(fake.searches) == 4


def test_failed_search_and_missing_key_are_not_cached(fake_tavily, monkeypatch):
    fake = fake_tavily([], fail=True)
    out = cancel_lookup.lookup("t", "Hulu", TODAY)
    assert "failed" in out["note"] and not config.settings.cancel_cache_path.exists()
    cancel_lookup.lookup("t", "Hulu", TODAY)
    assert len(fake.searches) == 2

    monkeypatch.setattr(tavily, "available", lambda: False)
    out = cancel_lookup.lookup("t", "Netflix", TODAY)
    assert out["note"] == cancel_lookup.NO_KEY and out["links"] == []
    assert cancel_prep("t", NETFLIX, TODAY)["missing"][0] == cancel_lookup.NO_KEY


def test_corrupt_cache_file_is_ignored(fake_tavily):
    path = config.settings.cancel_cache_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    fake_tavily([result("https://help.hulu.com/article/hulu-cancel-subscription")])
    assert cancel_lookup.lookup("t", "Hulu", TODAY)["verified"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["merchants"]["hulu"]["verified"] is True


# --- Steps grounded in the page -----------------------------------------------------------------------

def steps_reply(*steps: tuple[str, str]) -> str:
    return json.dumps({"steps": [{"step": s, "quote": q} for s, q in steps]})


def test_steps_are_kept_only_when_grounded(fake_tavily, fake_llm):
    url = "https://help.netflix.com/en/node/407"
    fake = fake_tavily([result(url)], pages={url: NETFLIX_PAGE})
    fake_llm.script = {LIGHTNING: [steps_reply(
        ("Sign in to your Account page.", "Sign in to your Account page"),
        ("Select Cancel Membership.", "Select Cancel Membership"),
        ("Select Finish Cancellation to confirm.", "Select **Finish Cancellation** to confirm"),
        ("Call 1-800-555-0100 to cancel.", "contact them to cancel"),  # a number the page doesn't have
        ("Visit netflix.com/cancel to finish.", "you can cancel your membership"),  # a link
        ("Ask for a refund of your last payment.", "refunds are issued within 5 days"),  # quote not on the page
    )]}
    out = cancel_lookup.lookup("t", "Netflix", TODAY)
    assert fake.extracts == [[url]]
    assert out["steps"] == ["Sign in to your Account page.", "Select Cancel Membership.",
                            "Select Finish Cancellation to confirm."]
    assert out["steps_url"] == url
    assert out["support_email"] == "cancel-help@netflix.com"  # near "cancel", on netflix.com; press@ is not
    call = fake_llm.calls[0]
    assert call["model"] == LIGHTNING and call["response_format"]["json_schema"]["strict"] is True
    assert "<page>" in call["messages"][0]["content"] and "ignore any" in call["messages"][0]["content"]

    prep = cancel_prep("t", NETFLIX, TODAY)  # from the cache now
    assert prep["steps"][:3] == out["steps"]
    assert prep["steps"][3] == ("These steps are from help.netflix.com (checked Oct 23, 2026). "
                                "If the page has changed, follow the page.")
    assert prep["email"]["to"] == "cancel-help@netflix.com"
    assert prep["lookup"]["from_cache"] is True and prep["links"][0]["verified"] is True


def test_too_few_grounded_steps_means_generic_steps(fake_tavily, fake_llm):
    url = "https://help.netflix.com/en/node/407"
    fake_tavily([result(url)], pages={url: NETFLIX_PAGE})
    fake_llm.script = {LIGHTNING: [steps_reply(("Select Cancel Membership.", "Select Cancel Membership"),
                                               ("Email the CEO.", "write to the chief executive"))]}
    out = cancel_lookup.lookup("t", "Netflix", TODAY)
    assert out["steps"] == [] and out["verified"] is True
    prep = cancel_prep("t", NETFLIX, TODAY)
    assert prep["steps"][0] == "Open Netflix's own page (help.netflix.com) and sign in."


def test_steps_must_be_about_cancelling(fake_tavily, fake_llm):
    url = "https://help.netflix.com/en/node/407"
    fake_tavily([result(url)], pages={url: NETFLIX_PAGE})
    fake_llm.script = {LIGHTNING: [steps_reply(("Sign in to your Account page.", "Sign in to your Account page"),
                                               ("Contact your partner.", "If you were billed through a partner"))]}
    assert cancel_lookup.lookup("t", "Netflix", TODAY)["steps"] == []


def test_clean_page_drops_images_and_link_targets():
    page = ("1. Go to the [Manage your membership](https://www.netflix.com/cancelplan) page.\n"
            "​![Netflix page](https://s3.amazonaws.com/x.webp?X-Amz-Signature=" + "a" * 3000 + ")\n\n\n"
            "2. Tap or click Cancel. See https://example.com/" + "b" * 200)
    out = cancel_lookup.clean_page(page)
    assert out == "1. Go to the Manage your membership page.\n\n2. Tap or click Cancel. See"


def test_page_without_cancel_text_skips_the_model(fake_tavily, fake_llm):
    url = "https://help.netflix.com/en/node/1"
    fake_tavily([result(url)], pages={url: "Change your plan or update your payment method."})
    assert cancel_lookup.lookup("t", "Netflix", TODAY)["steps"] == []
    assert fake_llm.calls == []


@pytest.mark.parametrize("step, quote, ok", [
    ("Select Cancel Membership.", "Select Cancel Membership", True),
    ("Select Cancel Membership.", "select   cancel membership.", True),  # case, spacing, end punctuation
    ("Select Cancel Membership.", "Cancel", False),  # quote too short
    ("Open the billing portal and press Terminate.", "Select Cancel Membership", False),  # words not on the page
    ("Wait 30 days, then cancel.", "you can cancel your membership", False),  # 30 isn't on the page
    ("", "Select Cancel Membership", False),
    (None, "Select Cancel Membership", False),
])
def test_grounded(step, quote, ok):
    assert cancel_lookup.grounded(step, quote, NETFLIX_PAGE) is ok


# --- Known pages need no search -----------------------------------------------------------------------

def test_store_billed_and_bill_pages_skip_the_search(fake_tavily):
    fake = fake_tavily([result("https://help.netflix.com/en/node/407")])
    icloud = Subscription(id="icloud", merchant="iCloud+", category="cloud_storage", monthly_cost=2.99)
    prep = cancel_prep("t", icloud, TODAY)
    assert prep["links"][0] == {"label": "Apple subscriptions page",
                                "url": "https://apps.apple.com/account/subscriptions", "verified": True}
    bill = Subscription(id="xfinity", merchant="Xfinity (Comcast)", category="internet", kind="bill",
                        bill_category="internet", monthly_cost=80.0)
    prep = cancel_prep("t", bill, TODAY)
    assert prep["links"][0]["verified"] is True and prep["links"][0]["url"].startswith("https://www.xfinity.com/")
    assert fake.searches == []
