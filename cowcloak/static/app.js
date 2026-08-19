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

document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    await navigator.clipboard.writeText(button.dataset.copy);
    const original = button.textContent;
    button.textContent = copiedLabel;
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
  button.textContent = copiedLabel;
  setTimeout(() => { button.textContent = original; }, 1200);
});

document.querySelectorAll('[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
});

document.querySelector('[data-page-size]')?.addEventListener('change', (event) => {
  event.currentTarget.form?.submit();
});
