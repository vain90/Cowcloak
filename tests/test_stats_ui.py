from pathlib import Path

from fastapi.templating import Jinja2Templates

import cowcloak
from cowcloak.aliases import AliasRecord
from cowcloak.config import Settings
from cowcloak.i18n import translations
from cowcloak.usage import mailbox_usage_enabled

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


async def test_mailbox_usage_tag_enables_dashboard_stats_without_domain_lookup():
    mailcow = FakeMailcow(mailbox_tags=["Cowcloak-Stats"])

    assert await mailbox_usage_enabled(settings(), mailcow, "user@example.org")
    assert mailcow.mailbox_calls == 1
    assert mailcow.domain_calls == 0


async def test_domain_usage_tag_enables_dashboard_stats():
    mailcow = FakeMailcow(domain_tags=["cowcloak-stats"])

    assert await mailbox_usage_enabled(settings(), mailcow, "user@example.org")
    assert mailcow.mailbox_calls == 1
    assert mailcow.domain_calls == 1


async def test_stats_disabled_skips_mailcow_usage_lookup():
    mailcow = FakeMailcow(mailbox_tags=["cowcloak-stats"])

    assert not await mailbox_usage_enabled(
        settings(enabled=False),
        mailcow,
        "user@example.org",
    )
    assert mailcow.mailbox_calls == 0
    assert mailcow.domain_calls == 0


def render_dashboard(*, stats_visible: bool) -> str:
    alias = AliasRecord(
        id=1,
        address="shop@example.org",
        goto="user@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="Shop",
        sogo_visible=True,
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
        usage_stats_visible=stats_visible,
        usage_stats={
            "shop@example.org": {
                "received_count": 7,
                "sent_count": 3,
                "last_used_at": 1787167766,
            }
        },
    )


def test_dashboard_renders_usage_counts_and_local_timestamp_marker():
    html = render_dashboard(stats_visible=True)

    assert "Nutzungsstatistik aktiv" in html
    assert "7</span> empfangen" in html
    assert "3</span> gesendet" in html
    assert 'data-local-timestamp="1787167766"' in html


def test_dashboard_hides_usage_ui_when_stats_are_not_available():
    html = render_dashboard(stats_visible=False)

    assert 'class="usage-summary"' not in html
    assert "Nutzungsstatistik aktiv" not in html
