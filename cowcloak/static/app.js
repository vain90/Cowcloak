const modeSelect = document.querySelector('[data-mode-select]');
const customLocalPart = document.querySelector('[data-custom-local-part]');

function syncAliasMode() {
  if (!modeSelect || !customLocalPart) return;
  customLocalPart.classList.toggle('hidden', modeSelect.value !== 'custom');
}

modeSelect?.addEventListener('change', syncAliasMode);
syncAliasMode();

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    await navigator.clipboard.writeText(button.dataset.copy);
    const original = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = original; }, 1200);
  });
});

document.querySelector('[data-copy-pool]')?.addEventListener('click', async (event) => {
  const addresses = [...document.querySelectorAll('[data-pool-address]')]
    .map((element) => element.textContent.trim())
    .join('\n');
  await navigator.clipboard.writeText(addresses);
  const button = event.currentTarget;
  const original = button.textContent;
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = original; }, 1200);
});

const search = document.querySelector('[data-search]');
search?.addEventListener('input', () => {
  const needle = search.value.trim().toLowerCase();
  document.querySelectorAll('[data-search-text]').forEach((row) => {
    row.hidden = !row.dataset.searchText.includes(needle);
  });
});
