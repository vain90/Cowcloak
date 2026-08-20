(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';
  const text = {
    de: {
      addressExpected: 'E-Mail erwartet',
      domainExpected: 'Domain erwartet',
      specificUnexpected: 'Nicht erwartet',
      title: 'Gesamte Domain als erwartet markieren?',
      body: (domain) =>
        `Dadurch werden alle Absender von ${domain} für diesen Alias als erwartet behandelt.\n\nBei großen oder öffentlichen Mailanbietern wie Gmail, Outlook oder Yahoo ist das normalerweise nicht empfehlenswert.`,
      confirm: 'Domain als erwartet markieren',
      failed: 'Die Domain konnte nicht als erwartet markiert werden.',
    },
    en: {
      addressExpected: 'Email expected',
      domainExpected: 'Domain expected',
      specificUnexpected: 'Unexpected',
      title: 'Mark the entire domain as expected?',
      body: (domain) =>
        `All senders from ${domain} will be treated as expected for this alias.\n\nThis is usually not recommended for large or public mail providers such as Gmail, Outlook or Yahoo.`,
      confirm: 'Mark domain as expected',
      failed: 'The domain could not be marked as expected.',
    },
  }[language];

  const REOPEN_KEY = 'moolias-unexpected-review-reopen';

  const isFullMode = () => document.body.dataset.statsEffective === 'full';

  function senderKey(form) {
    return form.querySelector('input[name="sender_key"]')?.value?.trim().toLowerCase() || '';
  }

  function decisionInput(form) {
    return form.querySelector('input[name="decision"]');
  }

  function aliasId(form) {
    const match = form.getAttribute('action')?.match(/^\/aliases\/(\d+)\/sender-expectation$/);
    return match?.[1] || null;
  }

  function preserveReviewContext(element) {
    if (!element.closest('dialog[data-unexpected-review-dialog]')) return;
    try {
      sessionStorage.setItem(REOPEN_KEY, '1');
    } catch (error) {
      console.debug('sessionStorage is unavailable', error);
    }
  }

  function decorateForm(form) {
    const key = senderKey(form);
    const decision = decisionInput(form);
    if (!key.includes('@') || !decision) return;

    if (decision.value === 'expected') {
      const addressButton = form.querySelector('button[type="submit"]');
      if (addressButton) addressButton.textContent = text.addressExpected;

      if (!form.querySelector('[data-expect-domain]')) {
        const button = document.createElement('button');
        button.className = 'button compact ghost';
        button.type = 'button';
        button.dataset.expectDomain = '1';
        button.textContent = text.domainExpected;
        form.append(button);
      }
    }

    if (decision.value === 'clear' && !form.querySelector('[data-specific-unexpected]')) {
      const button = document.createElement('button');
      button.className = 'button compact ghost';
      button.type = 'button';
      button.dataset.specificUnexpected = '1';
      button.textContent = text.specificUnexpected;
      form.append(button);
    }
  }

  function decorate(root = document) {
    if (!isFullMode()) return;
    if (root.matches?.('.sender-review-form')) decorateForm(root);
    root.querySelectorAll?.('.sender-review-form').forEach(decorateForm);
  }

  document.addEventListener('click', async (event) => {
    const domainButton = event.target.closest?.('[data-expect-domain]');
    if (domainButton) {
      const form = domainButton.closest('.sender-review-form');
      const key = form && senderKey(form);
      const id = form && aliasId(form);
      const csrfToken = form?.querySelector('input[name="csrf_token"]')?.value;
      if (!form || !key || !id || !csrfToken || !key.includes('@')) return;

      const domain = key.slice(key.lastIndexOf('@') + 1);
      const accepted = await window.MooliasDialog.confirm({
        title: text.title,
        message: text.body(domain),
        confirmLabel: text.confirm,
        tone: 'warning',
        dismissOnBackdrop: false,
      });
      if (!accepted) return;

      const payload = new FormData();
      payload.append('csrf_token', csrfToken);
      payload.append('sender_key', key);
      domainButton.disabled = true;
      try {
        const response = await fetch(`/aliases/${id}/sender-domain-expectation`, {
          method: 'POST',
          body: payload,
          credentials: 'same-origin',
        });
        if (response.status === 401) {
          window.location.assign('/');
          return;
        }
        if (!response.ok) {
          throw new Error(`Domain expectation failed with HTTP ${response.status}`);
        }
        preserveReviewContext(form);
        window.location.reload();
      } catch (error) {
        console.error('Sender domain expectation failed', error);
        domainButton.disabled = false;
        await window.MooliasDialog.error(text.failed);
      }
      return;
    }

    const unexpectedButton = event.target.closest?.('[data-specific-unexpected]');
    if (!unexpectedButton) return;
    const form = unexpectedButton.closest('.sender-review-form');
    const decision = form && decisionInput(form);
    if (!form || !decision) return;
    decision.value = 'unexpected';
    preserveReviewContext(form);
    form.requestSubmit();
  });

  const start = () => {
    decorate();
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node instanceof Element) decorate(node);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
