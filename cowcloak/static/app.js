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

function bindBulkActions(root = document) {
  root.querySelectorAll('[data-bulk-toolbar]').forEach((toolbar) => {
    if (toolbar.dataset.bound === 'true') return;
    toolbar.dataset.bound = 'true';

    const region = toolbar.closest('[data-alias-results-region]') || root;
    const count = toolbar.querySelector('[data-selected-count]');
    const selectAll = toolbar.querySelector('[data-select-all]');
    const selectNone = toolbar.querySelector('[data-select-none]');
    const actionButtons = [...toolbar.querySelectorAll('[data-bulk-action]')];
    const selectedTemplate = toolbar.dataset.selectedTemplate || '{count} selected';
    const failureMessage = toolbar.dataset.bulkFailed || 'The bulk action could not be completed.';

    const checkboxes = () => [...region.querySelectorAll('[data-alias-select]')];
    const selected = () => checkboxes().filter((checkbox) => checkbox.checked);

    const sync = () => {
      const selectedCount = selected().length;
      if (count) {
        count.textContent = selectedTemplate.replace('{count}', String(selectedCount));
      }
      actionButtons.forEach((button) => {
        button.disabled = selectedCount === 0;
      });
    };

    checkboxes().forEach((checkbox) => checkbox.addEventListener('change', sync));

    selectAll?.addEventListener('click', () => {
      checkboxes().forEach((checkbox) => { checkbox.checked = true; });
      sync();
    });

    selectNone?.addEventListener('click', () => {
      checkboxes().forEach((checkbox) => { checkbox.checked = false; });
      sync();
    });

    actionButtons.forEach((button) => {
      button.addEventListener('click', async () => {
        const selectedAliases = selected();
        if (!selectedAliases.length) return;

        if (button.dataset.bulkAction === 'copy') {
          await navigator.clipboard.writeText(
            selectedAliases.map((checkbox) => checkbox.dataset.address).join('\n'),
          );
          const original = button.textContent;
          button.textContent = copiedLabel;
          setTimeout(() => { button.textContent = original; }, 1200);
          return;
        }

        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
        if (!csrfToken) {
          window.alert(failureMessage);
          return;
        }

        const form = new FormData();
        form.append('csrf_token', csrfToken);
        form.append('action', button.dataset.bulkAction);
        selectedAliases.forEach((checkbox) => form.append('alias_ids', checkbox.value));

        actionButtons.forEach((actionButton) => { actionButton.disabled = true; });
        try {
          const response = await fetch('/aliases/bulk', {
            method: 'POST',
            body: form,
          });
          if (!response.ok) {
            throw new Error(`Bulk action failed with HTTP ${response.status}`);
          }
          window.location.reload();
        } catch (error) {
          console.error('Bulk alias action failed', error);
          window.alert(failureMessage);
          sync();
        }
      });
    });

    sync();
  });
}

function bindDynamicControls(root = document) {
  bindCopyButtons(root);
  bindConfirmForms(root);
  bindPageSize(root);
  bindAssignDialogs(root);
  bindBulkActions(root);
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

document.addEventListener('pointerdown', (event) => {
  document.querySelectorAll('details.alias-edit-action[open]').forEach((details) => {
    if (!details.contains(event.target)) {
      details.removeAttribute('open');
    }
  });
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
