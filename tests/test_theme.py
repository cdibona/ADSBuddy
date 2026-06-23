from pathlib import Path

CSS = Path("app/static/app.css").read_text()

class TestThemeTokens:
    def test_night_root_tokens_present(self):
        assert ":root" in CSS
        for tok in ("--bg", "--panel", "--ink", "--accent", "--ok", "--danger",
                    "--font-data", "--font-ui", "--radius"):
            assert tok in CSS, f"missing token {tok}"

    def test_day_override_block_present(self):
        assert '[data-theme="day"]' in CSS

    def test_no_legacy_hardcoded_bg(self):
        # The old hardcoded slate bg must be gone from component rules
        # (allowed only as a token value definition).
        assert CSS.count("#0f1216") <= 1
