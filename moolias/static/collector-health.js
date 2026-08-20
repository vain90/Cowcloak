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
      headroom: (percent) => `Historienpuffer ${percent} %`,
      headroomPending: 'Historienpuffer wird ermittelt',
      gapHeadroom: 'Historienpuffer nicht abgedeckt',
      limitReached: 'Limit erreicht',
      details: 'Collector-Details',
      lastAttempt: 'Letzter Versuch',
      lastSuccess: 'Letzter Erfolg',
      duration: 'Dauer des letzten Laufs',
      pollInterval: 'Poll-Intervall',
      staleThreshold: 'Veraltet nach',
      historyWindow: 'Rspamd-Historie',
      oldest: 'Ältester Eintrag',
      newest: 'Neuester Eintrag',
      previousWatermark: 'Vorheriger Watermark',
      currentWatermark: 'Aktueller Watermark',
      coverage: 'Historienpuffer',
      lastError: 'Letzter Fehler',
      never: 'noch nie',
      none: 'nicht vorhanden',
      notRequested: 'in diesem Lauf nicht abgefragt',
      ms: (value) => `${value} ms`,
      seconds: (value) => `${value} s`,
      stalePolls: (polls, seconds) => `${polls} Polls (${seconds} s)`,
      historyCount: (count, limit) => `${count} Einträge geladen · Maximum ${limit}`,
      coverageValue: (percent, overlap, count) =>
        `${percent} % (${overlap} von ${count} Einträgen liegen vor dem vorherigen Watermark)`,
      coverageInitial: 'Noch keine zwei erfolgreichen Historienfenster zum Vergleichen.',
      coverageUnavailable: 'In diesem Lauf wurde keine Rspamd-Historie benötigt.',
      coverageUnknown: 'Die Überlappung konnte aus den gelieferten Zeitstempeln nicht bestimmt werden.',
      coverageGap: 'Der vorherige Watermark liegt nicht mehr sicher im aktuellen Historienfenster.',
      coverageExplanation:
        'Der Historienpuffer ist der Anteil der aktuell geladenen Rspamd-History-Einträge, deren Zeitstempel älter als der Watermark des vorherigen erfolgreichen Polls ist. Moolias lädt die Historie adaptiv und zielt auf mindestens 10 % Überlappung. Der Wert beschreibt die Überlappung der History-Fenster, nicht CPU- oder Serverauslastung.',
      fullWarning:
        'Moolias musste bis zum konfigurierten History-Maximum laden. Das ist ein Warnsignal für ein knappes Fenster, aber allein kein Beweis für verlorene Daten.',
    },
    en: {
      states: {
        healthy: 'OK',
        low: 'low headroom',
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
      headroom: (percent) => `history headroom ${percent} %`,
      headroomPending: 'history headroom is being established',
      gapHeadroom: 'history watermark not covered',
      limitReached: 'limit reached',
      details: 'Collector details',
      lastAttempt: 'Last attempt',
      lastSuccess: 'Last success',
      duration: 'Last collection duration',
      pollInterval: 'Poll interval',
      staleThreshold: 'Stale after',
      historyWindow: 'Rspamd history',
      oldest: 'Oldest entry',
      newest: 'Newest entry',
      previousWatermark: 'Previous watermark',
      currentWatermark: 'Current watermark',
      coverage: 'History headroom',
      lastError: 'Last error',
      never: 'never',
      none: 'none',
      notRequested: 'not requested in this run',
      ms: (value) => `${value} ms`,
      seconds: (value) => `${value} s`,
      stalePolls: (polls, seconds) => `${polls} polls (${seconds} s)`,
      historyCount: (count, limit) => `${count} entries loaded · maximum ${limit}`,
      coverageValue: (percent, overlap, count) =>
        `${percent} % (${overlap} of ${count} entries are older than the previous watermark)`,
      coverageInitial: 'Two successful history windows are not available for comparison yet.',
      coverageUnavailable: 'Rspamd history was not needed in this collection run.',
      coverageUnknown: 'Overlap could not be determined from the returned timestamps.',
      coverageGap: 'The previous watermark is no longer safely inside the current history window.',
      coverageExplanation:
        'History headroom is the proportion of currently loaded Rspamd history entries whose timestamps are older than the watermark from the previous successful poll. Moolias loads history adaptively and targets at least 10% overlap. It measures overlap between history windows, not CPU or server utilization.',
      fullWarning:
        'Moolias had to load up to the configured history maximum. This is a warning signal that the window may be tight, but it is not proof that data was missed.',
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

    const headroom = percentage(payload.headroom_percent);
    if (payload.coverage_state === 'initial') {
      parts.push(text.headroomPending);
    } else if (headroom !== null && ['healthy', 'low'].includes(payload.state)) {
      parts.push(text.headroom(headroom));
    } else if (payload.state === 'gap') {
      parts.push(text.gapHeadroom);
    }
    if (payload.history_full) parts.push(text.limitReached);
    badge.textContent = parts.join(' · ');
    titleRow.append(badge);

    const details = document.createElement('details');
    details.className = 'collector-health-details';
    const summary = document.createElement('summary');
    summary.textContent = text.details;
    const list = document.createElement('dl');
    list.className = 'collector-health-grid';

    addDetail(list, text.lastAttempt, payload.last_attempt_at ? timestamp(payload.last_attempt_at) : text.never);
    addDetail(list, text.lastSuccess, payload.last_success_at ? timestamp(payload.last_success_at) : text.never);
    addDetail(
      list,
      text.duration,
      payload.last_duration_ms === null || payload.last_duration_ms === undefined
        ? text.none
        : text.ms(payload.last_duration_ms),
    );
    addDetail(list, text.pollInterval, text.seconds(payload.poll_interval_seconds));
    addDetail(
      list,
      text.staleThreshold,
      text.stalePolls(payload.stale_polls, payload.stale_after_seconds),
    );
    addDetail(
      list,
      text.historyWindow,
      payload.history_count === null || payload.history_count === undefined
        ? text.notRequested
        : text.historyCount(payload.history_count, payload.history_limit),
    );
    addDetail(list, text.oldest, payload.oldest_event_at ? timestamp(payload.oldest_event_at) : text.none);
    addDetail(list, text.newest, payload.newest_event_at ? timestamp(payload.newest_event_at) : text.none);
    addDetail(
      list,
      text.previousWatermark,
      payload.previous_watermark ? timestamp(payload.previous_watermark) : text.none,
    );
    addDetail(
      list,
      text.currentWatermark,
      payload.watermark ? timestamp(payload.watermark) : text.none,
    );

    let coverageValue = text.coverageUnknown;
    if (payload.coverage_state === 'initial') coverageValue = text.coverageInitial;
    else if (payload.coverage_state === 'unavailable') coverageValue = text.coverageUnavailable;
    else if (payload.coverage_state === 'gap') coverageValue = text.coverageGap;
    else if (headroom !== null) {
      coverageValue = text.coverageValue(headroom, payload.overlap_count, payload.history_count);
    }
    addDetail(list, text.coverage, coverageValue);
    if (payload.last_error) addDetail(list, text.lastError, payload.last_error);

    const explanation = document.createElement('p');
    explanation.className = 'collector-health-explanation';
    explanation.textContent = text.coverageExplanation;
    details.append(summary, list, explanation);

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
