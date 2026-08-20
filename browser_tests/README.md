# Browser E2E tests

The browser suite exercises Moolias through a real Chromium browser while using a deterministic test-only Mailcow implementation. It does not contact a real Mailcow server or the public internet.

Install the normal development dependencies and Chromium once:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m playwright install chromium
```

Run the suite with the same diagnostics used in CI:

```bash
pytest -q browser_tests \
  --browser chromium \
  --tracing retain-on-failure \
  --screenshot only-on-failure \
  --output test-results
```

The tests start a local Uvicorn server on an ephemeral loopback port. `browser_tests/e2e_app.py` replaces Mailcow and OAuth only inside that test process; no production test mode is enabled in Moolias itself.

Failed tests retain Playwright screenshots and traces under `test-results/`. GitHub Actions uploads that directory as the `browser-e2e-results` artifact when the browser job fails.
