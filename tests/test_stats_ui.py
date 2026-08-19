from pathlib import Path

from fastapi.templating import Jinja2Templates

import cowcloak
from cowcloak.aliases import AliasRecord
from cowcloak.config import Settings
from cowcloak.i18n import translations
from cowcloak.stats_mode import StatsMode, StatsModeSource, StatsModeState
from cowcloak.usage import mailbox_stats_state, mailbox_usage_enabled

TEMPLATES = Jinja2Templates(directory=str(Path(cowcloak.__file__).resolve().parent / "templates"))


def settings(*, enabled: bool = True) -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_USAGE_STATS=enabled,
        COWCLOAK_USAGE_TAG="cowcloak-stats",
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, *, mailbox_tags=(), domain_tags=()) -> None:
        self.mailbox_tags = list(mailbox_tags)
        self.domain_tags = list(domain_tags)
        self.mailbox_calls = 0
        self.domain_calls = 0

    async def get_mailbox(self, email: str):
        self.mailbox_calls += 1
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[1],
            "tags": self.mailbox_tags,
        }

    async def get_domain(self, domain: str):
        self.domain_calls += 1
        return {"domain": domain, "tags": self.domain_tags}


async def test_mailbox_mode_is_visible_as_effective_state():
    mailcow = FakeMailcow(
        mailbox_tags=["cowcloak-stats-domain"],
        domain_tags=["cowcloak-stats-full"],
    )

    state = await mailbox_stats_state(settings(), mailcow, "user@example.org")

    assert state.effective is StatsMode.DOMAIN
    assert state.source is StatsModeSource.MAILBOX
    assert await mailbox_usage_enabled(settings(), mailcow, "user@example.org")


async def test_stats_disabled_skips_mailcow_lookup():
    mailcow = FakeMailcow(mailbox_tags=["cowcloak-stats-full"])

    state = await mailbox_stats_state(settings(enabled=False), mailcow, "user@example.org")

    assert state.effective is StatsMode.OFF
    assert mailcow.mailbox_calls == 0
    assert mailcow.domain_calls == 0


def render_dashboard(*, mode: StatsMode = StatsMode.FULL) -> str:
    alias = AliasRecord(
        id=1,
        address="amazon-k7@example.org",
        goto="user@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="Amazon",
        sogo_visible=True,
    )
    state = StatsModeState(
        effective=mode,
        source=StatsModeSource.MAILBOX,
        mailbox_override=mode,
        domain_default=StatsMode.BASIC,
    )
    return TEMPLATES.get_template("dashboard.html").render(
        language="de",
        t=translations("de"),
        return_to="/aliases",
        version="0.1.3",
        user="user@example.org",
        domain="example.org",
        catch_all=None,
        assigned=[alias],
        assigned_total=1,
        filtered_total=1,
        reserved=[],
        csrf_token="csrf",
        search_query="",
        status_filter="all",
        status_counts={"all": 1, "active": 1, "disabled": 0},
        page=1,
        per_page=25,
        page_sizes=(10, 25, 50, 100),
        total_pages=1,
        pagination_items=[1],
        range_start=1,
        range_end=1,
        stats_available=True,
        stats_error=False,
        stats_state=state,
        stats_mode_selection=mode.value,
        usage_stats_visible=mode is not StatsMode.OFF,
        usage_stats={
            "amazon-k7@example.org": {
                "received_count": 7,
                "sent_count": 3,
                "last_used_at": 1787167766,
            }
        },
        sender_stats={
            "amazon-k7@example.org": [
                {
                    "sender_key": "news@amazon.de",
                    "label": "news@amazon.de",
                    "domain": "amazon.de",
                    "received_count": 6,
                    "last_received_at": 1787167766,
                    "expected": True,
                    "review_source": "automatic",
                    "manual_expected": None,
                    "match_token": "amazon",
                },
                {
                    "sender_key": "odd@unexpected.example",
                    "label": "odd@unexpected.example",
                    "domain": "unexpected.example",
                    "received_count": 1,
                    "last_received_at": 1787167700,
                    "expected": False,
                    "review_source": "unreviewed",
                    "manual_expected": None,
                    "match_token": None,
                },
            ]
        },
    )


def test_dashboard_renders_mode_usage_counts_and_sender_review():
    html = render_dashboard()

    assert "Nutzungsstatistik" in html
    assert "Vollständig" in html
    assert "Postfach-Einstellung" in html
    assert "7</span> empfangen" in html
    assert "3</span> gesendet" in html
    assert 'data-local-timestamp="1787167766"' in html
    assert "sender-stats-row expected" in html
    assert "sender-stats-row unexpected" in html
    assert "Automatisch erkannt" in html
    assert "amazon" in html
    assert "Als erwartet markieren" in html
    assert "1 unerwartet" in html


def test_basic_mode_hides_sender_details_but_keeps_usage_counts():
    html = render_dashboard(mode=StatsMode.BASIC)

    assert 'class="usage-summary"' in html
    assert 'class="sender-stats"' not in html


def test_off_mode_hides_usage_and_sender_details_but_shows_setting():
    html = render_dashboard(mode=StatsMode.OFF)

    assert "Nutzungsstatistik" in html
    assert 'class="usage-summary"' not in html
    assert 'class="sender-stats"' not in html
