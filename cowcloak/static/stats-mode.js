const statsModeForm = document.querySelector('.usage-mode-form');

if (statsModeForm) {
  const select = statsModeForm.querySelector('select[name="mode"]');
  const ranks = { off: 0, basic: 1, domain: 2, full: 3 };
  const labels = {
    de: {
      off: 'Aus',
      basic: 'Standard',
      domain: 'Domains',
      full: 'Vollständig',
    },
    en: {
      off: 'Off',
      basic: 'Standard',
      domain: 'Domains',
      full: 'Full',
    },
  };
  const language = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';

  statsModeForm.addEventListener('submit', (event) => {
    const current = document.body.dataset.statsEffective || 'off';
    const domainDefault = document.body.dataset.statsDomain || 'off';
    const selection = select?.value || 'inherit';
    const target = selection === 'inherit' ? domainDefault : selection;

    if (!(current in ranks) || !(target in ranks) || ranks[target] >= ranks[current]) {
      return;
    }

    const message = language === 'de'
      ? `Du wechselst die Nutzungsstatistik von „${labels.de[current]}“ auf „${labels.de[target]}“. Daten, die der niedrigere Modus nicht speichern darf, werden dabei dauerhaft gelöscht. Dieser Schritt kann nicht rückgängig gemacht werden.\n\nMöchtest du fortfahren?`
      : `You are changing usage statistics from “${labels.en[current]}” to “${labels.en[target]}”. Data that the lower mode is not allowed to retain will be permanently deleted. This cannot be undone.\n\nDo you want to continue?`;

    if (!window.confirm(message)) {
      event.preventDefault();
      return;
    }

    let confirmed = statsModeForm.querySelector('input[name="confirm_downgrade"]');
    if (!confirmed) {
      confirmed = document.createElement('input');
      confirmed.type = 'hidden';
      confirmed.name = 'confirm_downgrade';
      statsModeForm.append(confirmed);
    }
    confirmed.value = '1';
  });
}
