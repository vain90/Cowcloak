const modeOptions = [...document.querySelectorAll('[data-mode-option]')];
const customLocalPart = document.querySelector('[data-custom-local-part]');
const copiedLabel = document.body.dataset.copiedLabel || 'Copied';

function syncAliasMode() {
  if (!customLocalPart) return;
  const selected = modeOptions.find((option) => option.checked)?.value;
  customLocalPart.classList.toggle('hidden', selected !== 'custom');
}

modeOptions.forEach((option) => option.addEventListener('change', syncAliasMode));
syncAliasMode();

function bindCopyButtons(root = document) {
  root.querySelectorAll('[data-copy]').forEach((button) => {
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', async () => {
      await navigator.clipboard.writeText(button.dataset.copy);
      const original = button.textContent;
      button.textContent = copiedLabel;
      setTimeout(() => { button.textContent = original; }, 1200);
    });
  });
}

function bindConfirmForms(root = document) {
  root.querySelectorAll('[data-confirm]').forEach((form) => {
    if (form.dataset.bound === 'true') return;
    form.dataset.bound = 'true';
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
}

function bindPageSize(root = document) {
  root.querySelectorAll('[data-page-size]').forEach((select) => {
    if (select.dataset.bound === 'true') return;
    select.dataset.bound = 'true';
    select.addEventListener('change', (event) => {
      event.currentTarget.form?.submit();
    });
  });
}

function bindAssignDialogs(root = document) {
  root.querySelectorAll('[data-open-assign-dialog]').forEach((button) => {
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', () => {
      const dialogId = button.dataset.openAssignDialog;
      const dialog = document.querySelector(`[data-assign-dialog="${dialogId}"]`);
      dialog?.showModal();
      dialog?.querySelector('input[name="description"]')?.focus();
    });
  });

  root.querySelectorAll('[data-assign-dialog]').forEach((dialog) => {
    if (dialog.dataset.bound === 'true') return;
    dialog.dataset.bound = 'true';
    dialog.querySelector('[data-close-dialog]')?.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });
}

function bindDynamicControls(root = document) {
  bindCopyButtons(root);
  bindConfirmForms(root);
  bindPageSize(root);
  bindAssignDialogs(root);
}

bindDynamicControls();

const helpDialog = document.querySelector('[data-help-dialog]');
document.querySelector('[data-open-help-dialog]')?.addEventListener('click', () => {
  helpDialog?.showModal();
});
helpDialog?.querySelector('[data-close-help-dialog]')?.addEventListener('click', () => {
  helpDialog.close();
});
helpDialog?.addEventListener('click', (event) => {
  if (event.target === helpDialog) {
    helpDialog.close();
  }
});

document.querySelector('[data-copy-pool]')?.addEventListener('click', async (event) => {
  const addresses = [...document.querySelectorAll('[data-pool-address]')]
    .map((element) => element.textContent.trim())
    .join('\n');
  await navigator.clipboard.writeText(addresses);
  const button = event.currentTarget;
  const original = button.textContent;
  button.textContent = copiedLabel;
  setTimeout(() => { button.textContent = original; }, 1200);
});

const searchInput = document.querySelector('[data-live-search]');
const searchClear = document.querySelector('[data-search-clear]');
let searchTimer;
let searchController;

function syncSearchClear() {
  if (!searchClear || !searchInput) return;
  searchClear.hidden = searchInput.value.length === 0;
}

async function refreshAliasResults() {
  if (!searchInput) return;

  const rawQuery = searchInput.value.trim();
  const activeQuery = rawQuery.length >= 2 ? rawQuery : '';
  const url = new URL(window.location.href);
  url.searchParams.set('status', searchInput.dataset.status || 'all');
  url.searchParams.set('per_page', searchInput.dataset.perPage || '25');
  url.searchParams.set('page', '1');
  if (activeQuery) {
    url.searchParams.set('q', activeQuery);
  } else {
    url.searchParams.delete('q');
  }

  searchController?.abort();
  searchController = new AbortController();
  searchInput.classList.add('searching');

  try {
    const response = await fetch(url, {
      headers: { 'X-Cowcloak-Partial': 'alias-results' },
      signal: searchController.signal,
    });
    if (!response.ok) return;

    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const nextRegion = parsed.querySelector('[data-alias-results-region]');
    const currentRegion = document.querySelector('[data-alias-results-region]');
    const nextSummary = parsed.querySelector('[data-assigned-summary]');
    const currentSummary = document.querySelector('[data-assigned-summary]');

    if (nextRegion && currentRegion) {
      currentRegion.innerHTML = nextRegion.innerHTML;
      bindDynamicControls(currentRegion);
    }
    if (nextSummary && currentSummary) {
      currentSummary.textContent = nextSummary.textContent.trim();
    }
    window.history.replaceState(null, '', `${url.pathname}${url.search}`);
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Alias search failed', error);
    }
  } finally {
    searchInput.classList.remove('searching');
  }
}

searchInput?.addEventListener('input', () => {
  syncSearchClear();
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(refreshAliasResults, 250);
});

searchClear?.addEventListener('click', () => {
  if (!searchInput) return;
  window.clearTimeout(searchTimer);
  searchInput.value = '';
  syncSearchClear();
  searchInput.focus();
  refreshAliasResults();
});

syncSearchClear();
