from datetime import UTC, datetime

from app.models import NotificationHistory
from app.services.email.providers import OutgoingEmail, SmtpProvider
from app.services.email.render import money, pct, render_notification, render_test


def _n(**kw):
    base = dict(id=42, alert_rule_id=None, notification_type="custom", severity="high", title="Spend <script>alert(1)</script> rose",
                message="Details & <b>more</b>", link="/alerts", entity_type=None, entity_id=None, dedup_key="x", is_demo=False,
                created_at=datetime(2026, 11, 6, 9, 0, tzinfo=UTC))
    base.update(kw)
    return NotificationHistory(**base)


def test_html_escapes_record_values_and_has_text_alternative():
    r = render_notification(None, _n())
    assert "<script>alert(1)</script>" not in r.html
    assert "&lt;script&gt;" in r.html
    assert "Details &amp; &lt;b&gt;more&lt;/b&gt;" in r.html
    assert "Spend <script>alert(1)</script> rose" in r.text  # plain text is not HTML
    assert "ACIP-N0000042" in r.html and "please do not reply" in r.html
    assert "Manage alert rules" in r.html and "never changes Azure resources" in r.html


def test_demo_label_and_subject_prefix():
    r = render_notification(None, _n(is_demo=True))
    assert r.subject.startswith("[DEMO] [ACIP")
    assert "DEMO DATA" in r.html and "DEMO DATA" in r.text


def test_test_email():
    r = render_test(["finops@example.com"])
    assert r.subject == "[ACIP · Test] Email delivery test"
    assert "Email delivery is working" in r.html and "finops@example.com" in r.html


def test_formatters():
    assert money(1234.5, "USD") == "$1,234.50"
    assert money(-10, "EUR") == "-€10.00"
    assert money(5, "USD", sign=True) == "+$5.00"
    assert money(7, "SEK") == "7.00 SEK"
    assert pct(31.26) == "+31.3%" and pct(None) == "n/a"


def test_smtp_message_structure():
    from app.core.config import Settings

    s = Settings(email_provider="smtp", email_from_address="acip@contoso.com", email_from_name="Azure Cost Intelligence", email_reply_to="finops@contoso.com")
    m = SmtpProvider(s).build(OutgoingEmail(to=["a@contoso.com", "b@contoso.com"], subject="S", html="<p>h</p>", text="t", headers={"X-ACIP-Type": "anomaly"}))
    assert m["From"] == "Azure Cost Intelligence <acip@contoso.com>"
    assert m["To"] == "a@contoso.com, b@contoso.com" and m["Reply-To"] == "finops@contoso.com"
    assert m["Auto-Submitted"] == "auto-generated" and m["X-Auto-Response-Suppress"] == "All"
    assert m.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in m.iter_parts()] == ["text/plain", "text/html"]
    assert m["Message-ID"].endswith("@contoso.com>")


def test_brand_tagline_never_repeats_product_name():
    r = render_test(["a@example.com"])
    bar = r.html.split("<!-- Brand bar -->")[1].split("<!-- Severity accent -->")[0]
    assert bar.count("Azure Cost Intelligence") == 1
    assert "Cost monitoring for Azure" in bar


def test_plain_text_keeps_one_item_per_line():
    r = render_test(["a@example.com"])
    lines = r.text.splitlines()
    assert any(line.startswith("Delivery: Successful") for line in lines)
    assert any(line.startswith("Sender: Azure Cost Intelligence") for line in lines)
    assert "DETAILS" in lines and "WHAT HAPPENS NEXT" in lines
    assert any(line.strip().startswith("1. Open Alerts") for line in lines)
