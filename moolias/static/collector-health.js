(() => {
  const titleRow = document.querySelector('.usage-settings-title-row');
  const settingsCopy = titleRow?.closest('.usage-settings-copy');
  if (!titleRow || !settingsCopy) return;

  const language = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';
  const text = {
    de: {
      states: {
        healthy: 'OK',
        low: 'Puffer niedrig',
        gap: 'mögliche Lücke',
        stale: 'veraltet',
        failed: 'Fehler',
        starting: 'startet',
      },
      unavailable: 'Status nicht verfügbar',
      ago: (seconds) => {
        if (seconds < 60) return `vor ${seconds} s`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `vor ${minutes} min`;
        const hours = Math.floor(minutes / 60);
        return `vor ${hours} h`;
      },
      details: 'Collector-Details',
      lastAttempt: 'Letzter Versuch',
      lastSuccess: 'Letzter Erfolg',
      historyBuffer: 'History-Puffer',
      historyFetch: 'History-Abruf',
      pollInterval: 'Poll-Intervall',
      lastError: 'Letzter Fehler',
      never: 'noch nie',
      none: 'nicht vorhanden',
      notRequested: 'in diesem Lauf nicht benötigt',
      seconds: (value) => `${value} s`,
      historyCount: (count, limit) => `${count} Einträge geladen · max. ${limit}`,
      probeFetch: '3 Einträge geprüft · unverändert',
      bufferValue: (percent) => `${percent} % frei`,
      bufferPending: 'wird nach einem vergleichbaren Lauf ermittelt',
      bufferGap: 'nicht sicher bestimmbar',
      bufferUnavailable: 'nicht verfügbar',
      fullWarning:
        'Moolias musste das konfigurierte History-Maximum laden. Wenn das wiederholt vorkommt oder der Puffer niedrig wird, sollte MOOLIAS_USAGE_HISTORY_COUNT geprüft werden.',
    },
    en: {
      states: {
        healthy: 'OK',
        low: 'low buffer',
        gap: 'possible gap',
        stale: 'stale',
        failed: 'failed',
        starting: 'starting',
      },
      unavailable: 'status unavailable',
      ago: (seconds) => {
        if (seconds < 60) return `${seconds} s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes} min ago`;
        const hours = Math.floor(minutes / 60);
        return `${hours} h ago`;
      },
      details: 'Collector details',
      lastAttempt: 'Last attempt',
      lastSuccess: 'Last success',
      historyBuffer: 'History buffer',
      historyFetch: 'History fetch',
      pollInterval: 'Poll interval',
      lastError: 'Last error',
      never: 'never',
      none: 'none',
      notRequested: 'not needed in this run',
      seconds: (value) => `${value} s`,
      historyCount: (count, limit) => `${count} entries loaded · max. ${limit}`,
      probeFetch: '3 entries checked · unchanged',
      bufferValue: (percent) => `${percent} % free`,
      bufferPending: 'will be established after a comparable run',
      bufferGap: 'cannot be determined safely',
      bufferUnavailable: 'unavailable',
      fullWarning:
        'Moolias had to load the configured history maximum. If this happens repeatedly or the buffer becomes low, review MOOLIAS_USAGE_HISTORY_COUNT.',
    },
  }[language];

  const timestamp = (seconds) => {
    if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return text.none;
    return new Intl.DateTimeFormat(document.documentElement.lang || undefined, {
      dateStyle: 'short',
      timeStyle: 'medium',
    }).format(new Date(Number(seconds) * 1000));
  };

  const percentage = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return null;
    const rounded = Math.round(numeric * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  };

  const addDetail = (list, label, value) => {
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    description.textContent = value;
    list.append(term, description);
  };

  const render = (payload) => {
    if (!payload?.enabled) return;

    const badge = document.createElement('span');
    badge.className = `collector-health-badge state-${payload.state || 'starting'}`;
    const parts = [`Collector: ${text.states[payload.state] || text.states.starting}`];

    if (payload.last_success_at) {
      const age = Math.max(0, Math.floor(Date.now() / 1000 - Number(payload.last_success_at)));
      parts.push(text.ago(age));
    }

    badge.textContent = parts.join(' · ');
    titleRow.append(badge);

    const details = document.createElement('details');
    details.className = 'collector-health-details';
    const summary = document.createElement('summary');
    summary.textContent = text.details;
    const list = document.createElement('dl');
    list.className = 'collector-health-grid';

    addDetail(
      list,
      text.lastSuccess,
      payload.last_success_at ? timestamp(payload.last_success_at) : text.never,
    );

    const buffer = percentage(payload.history_buffer_percent);
    let bufferValue = text.bufferUnavailable;
    if (payload.coverage_state === 'gap') bufferValue = text.bufferGap;
    else if (payload.coverage_state === 'initial') bufferValue = text.bufferPending;
    else if (buffer !== null) bufferValue = text.bufferValue(buffer);
    addDetail(list, text.historyBuffer, bufferValue);

    const probeUnchanged = payload.coverage_state === 'healthy-probe';
    const historyFetch = probeUnchanged
      ? text.probeFetch
      : payload.history_count === null || payload.history_count === undefined
        ? text.notRequested
        : text.historyCount(payload.history_count, payload.history_limit);
    addDetail(list, text.historyFetch, historyFetch);

    addDetail(list, text.pollInterval, text.seconds(payload.poll_interval_seconds));

    if (payload.last_error) {
      addDetail(
        list,
        text.lastAttempt,
        payload.last_attempt_at ? timestamp(payload.last_attempt_at) : text.never,
      );
      addDetail(list, text.lastError, payload.last_error);
    }

    details.append(summary, list);

    if (payload.history_full) {
      const warning = document.createElement('p');
      warning.className = 'collector-health-warning';
      warning.textContent = text.fullWarning;
      details.append(warning);
    }
    settingsCopy.append(details);
  };

  const renderUnavailable = () => {
    const badge = document.createElement('span');
    badge.className = 'collector-health-badge state-unavailable';
    badge.textContent = `Collector: ${text.unavailable}`;
    titleRow.append(badge);
  };

  fetch('/aliases/collector-health', { credentials: 'same-origin' })
    .then((response) => {
      if (!response.ok) throw new Error(`Collector health request failed with HTTP ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch((error) => {
      console.error('Could not load collector health', error);
      renderUnavailable();
    });
})();
