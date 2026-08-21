(() => {
  const path = window.location.pathname;
  if (path !== "/aliases") return;

  const topbar = document.querySelector(".topbar");
  const topControls = document.querySelector(".language-switch");
  if (!topbar || !topControls) return;

  const language = document.documentElement.lang === "de" ? "de" : "en";
  const copy = {
    de: {
      settings: "Einstellungen",
      settingsIntro: "Optionen, die du normalerweise nur selten ändern musst.",
      close: "Schließen",
      helpTitle: "Einstellungen",
      helpBody:
        "Über das Zahnrad oben rechts findest du den Schutz deiner Primäradresse und die Nutzungsstatistik. Wenn die Primäradresse ungeschützt ist, erinnert dich Moolias mit einem kleinen Hinweis daran.",
      title: "Primäradresse schützen",
      description:
        "Verhindert, dass deine eigentliche Mailbox-Adresse als Absender verwendet wird. Der Empfang bleibt unverändert.",
      toggle: "Primäradresse als Absender sperren",
      blocked: "Geschützt",
      allowed: "Senden erlaubt",
      external: "Extern geschützt",
      externalHint:
        "Diese Adresse wird bereits durch eine bestehende Mailcow/Postfix-Regel gesperrt und deshalb nicht von Moolias verwaltet.",
      warning: "Deine Primäradresse kann derzeit als Absender verwendet werden.",
      warningUnavailable: "Der Schutzstatus deiner Primäradresse kann derzeit nicht geprüft werden.",
      protect: "Schützen",
      openSettings: "Einstellungen öffnen",
      cooldown: (seconds) =>
        seconds === 1
          ? "Erneute Änderung in 1 Sekunde möglich."
          : `Erneute Änderung in ${seconds} Sekunden möglich.`,
      unavailable: "Absenderschutz ist derzeit nicht verfügbar.",
      missing:
        "Der Moolias Mailcow Agent wurde nicht gefunden. Bitte den Administrator informieren.",
      authentication:
        "Der Moolias Mailcow Agent ist erreichbar, aber die Authentifizierung ist fehlgeschlagen.",
      unreachable:
        "Der Moolias Mailcow Agent ist momentan nicht erreichbar.",
      failed: "Die Änderung konnte nicht gespeichert werden.",
    },
    en: {
      settings: "Settings",
      settingsIntro: "Options you normally only need to change occasionally.",
      close: "Close",
      helpTitle: "Settings",
      helpBody:
        "Use the gear in the top-right corner to manage primary-address protection and usage statistics. When the primary address is unprotected, Moolias shows a small reminder.",
      title: "Protect primary address",
      description:
        "Prevents your real mailbox address from being used as a sender. Receiving mail is unchanged.",
      toggle: "Block primary address as sender",
      blocked: "Protected",
      allowed: "Sending allowed",
      external: "Protected externally",
      externalHint:
        "This address is already blocked by an existing Mailcow/Postfix rule and is therefore not managed by Moolias.",
      warning: "Your primary address can currently be used as a sender.",
      warningUnavailable: "The protection status of your primary address cannot currently be checked.",
      protect: "Protect",
      openSettings: "Open settings",
      cooldown: (seconds) =>
        seconds === 1
          ? "You can change this again in 1 second."
          : `You can change this again in ${seconds} seconds.`,
      unavailable: "Sender protection is currently unavailable.",
      missing:
        "The Moolias Mailcow Agent was not found. Please contact the administrator.",
      authentication:
        "The Moolias Mailcow Agent is reachable, but authentication failed.",
      unreachable: "The Moolias Mailcow Agent is currently unreachable.",
      failed: "The change could not be saved.",
    },
  }[language];

  const usageSettings = document.querySelector(".usage-settings");
  let settingsButton = null;
  let settingsDialog = null;
  let settingsContent = null;
  let protectionSection = null;
  let toggle = null;
  let stateLabel = null;
  let message = null;
  let warning = null;
  let warningText = null;
  let warningButton = null;
  let featureEnabled = false;
  let currentAvailable = false;
  let currentBlocked = false;
  let externallyManaged = false;
  let countdownTimer = null;

  function csrfToken() {
    return document.querySelector('form[action="/logout"] input[name="csrf_token"]')?.value || "";
  }

  function openSettings() {
    ensureSettingsShell();
    if (!settingsDialog.open) settingsDialog.showModal();
    window.requestAnimationFrame(() => {
      if (protectionSection && featureEnabled) {
        protectionSection.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function augmentHelp() {
    const helpContent = document.querySelector(".help-content");
    if (!helpContent || helpContent.querySelector("[data-settings-help]")) return;

    const section = document.createElement("section");
    section.dataset.settingsHelp = "1";
    const heading = document.createElement("h3");
    heading.textContent = copy.helpTitle;
    const body = document.createElement("p");
    body.textContent = copy.helpBody;
    section.append(heading, body);
    helpContent.append(section);
  }

  function ensureSettingsShell() {
    if (settingsDialog) return settingsDialog;

    settingsButton = document.createElement("button");
    settingsButton.className = "settings-trigger";
    settingsButton.type = "button";
    settingsButton.dataset.openSettingsDialog = "1";
    settingsButton.setAttribute("aria-label", copy.settings);
    settingsButton.title = copy.settings;
    settingsButton.textContent = "⚙";

    const helpButton = topControls.querySelector("[data-open-help-dialog]");
    if (helpButton) {
      helpButton.insertAdjacentElement("beforebegin", settingsButton);
    } else {
      topControls.append(settingsButton);
    }

    settingsDialog = document.createElement("dialog");
    settingsDialog.className = "settings-dialog";
    settingsDialog.dataset.settingsDialog = "1";
    settingsDialog.innerHTML = `
      <div class="dialog-head">
        <div>
          <h2>${copy.settings}</h2>
          <p class="muted">${copy.settingsIntro}</p>
        </div>
        <button
          class="dialog-close"
          type="button"
          aria-label="${copy.close}"
          title="${copy.close}"
          data-close-settings-dialog
        >×</button>
      </div>
      <div class="settings-content" data-settings-content></div>
    `;
    document.body.append(settingsDialog);
    settingsContent = settingsDialog.querySelector("[data-settings-content]");

    settingsButton.addEventListener("click", openSettings);
    settingsDialog
      .querySelector("[data-close-settings-dialog]")
      ?.addEventListener("click", () => settingsDialog.close());
    settingsDialog.addEventListener("click", (event) => {
      if (event.target === settingsDialog) settingsDialog.close();
    });

    augmentHelp();
    return settingsDialog;
  }

  function moveUsageSettings() {
    if (!usageSettings) return;
    ensureSettingsShell();
    usageSettings.classList.add("settings-usage-section");
    settingsContent.append(usageSettings);
  }

  function ensureProtectionSection() {
    if (protectionSection) return protectionSection;

    ensureSettingsShell();
    protectionSection = document.createElement("section");
    protectionSection.className = "settings-section sender-protection-settings";
    protectionSection.dataset.senderProtectionSettings = "1";
    protectionSection.innerHTML = `
      <div class="sender-protection-copy">
        <div class="sender-protection-title-row">
          <h3>${copy.title}</h3>
          <span class="sender-protection-state"></span>
        </div>
        <p class="muted sender-protection-description">${copy.description}</p>
        <p class="sender-protection-message" aria-live="polite"></p>
      </div>
      <label class="sender-protection-control">
        <span>${copy.toggle}</span>
        <span class="sender-protection-switch">
          <input type="checkbox" role="switch" aria-label="${copy.toggle}">
          <span class="sender-protection-slider" aria-hidden="true"></span>
        </span>
      </label>
    `;

    settingsContent.prepend(protectionSection);
    toggle = protectionSection.querySelector('input[type="checkbox"]');
    stateLabel = protectionSection.querySelector(".sender-protection-state");
    message = protectionSection.querySelector(".sender-protection-message");
    toggle.addEventListener("change", save);
    return protectionSection;
  }

  function ensureWarning() {
    if (warning) return warning;

    warning = document.createElement("div");
    warning.className = "sender-protection-warning";
    warning.dataset.senderProtectionWarning = "1";

    warningText = document.createElement("span");
    warningText.className = "sender-protection-warning-text";

    warningButton = document.createElement("button");
    warningButton.className = "sender-protection-warning-action";
    warningButton.type = "button";
    warningButton.addEventListener("click", openSettings);

    warning.append(warningText, warningButton);
    topbar.insertAdjacentElement("afterend", warning);
    return warning;
  }

  function syncWarning() {
    if (!featureEnabled) {
      warning?.remove();
      warning = null;
      warningText = null;
      warningButton = null;
      return;
    }

    if (currentAvailable && (currentBlocked || externallyManaged)) {
      if (warning) warning.hidden = true;
      return;
    }

    ensureWarning();
    warning.hidden = false;
    warning.classList.toggle("is-unavailable", !currentAvailable);
    warningText.textContent = currentAvailable ? copy.warning : copy.warningUnavailable;
    warningButton.textContent = currentAvailable ? copy.protect : copy.openSettings;
  }

  function setState(blocked) {
    currentBlocked = Boolean(blocked);
    toggle.checked = currentBlocked;
    stateLabel.textContent = externallyManaged
      ? copy.external
      : currentBlocked
        ? copy.blocked
        : copy.allowed;
    stateLabel.classList.toggle("is-blocked", currentBlocked);
    syncWarning();
  }

  function stopCountdown() {
    if (countdownTimer !== null) {
      window.clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function startCountdown(seconds) {
    stopCountdown();
    if (externallyManaged) {
      toggle.disabled = true;
      message.classList.remove("is-error");
      message.textContent = copy.externalHint;
      return;
    }

    let remaining = Math.max(0, Number.parseInt(seconds, 10) || 0);
    if (remaining <= 0) {
      toggle.disabled = false;
      message.textContent = "";
      return;
    }

    toggle.disabled = true;
    message.classList.remove("is-error");
    message.textContent = copy.cooldown(remaining);

    countdownTimer = window.setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        stopCountdown();
        toggle.disabled = false;
        message.textContent = "";
        return;
      }
      message.textContent = copy.cooldown(remaining);
    }, 1000);
  }

  function unavailable(reason) {
    featureEnabled = true;
    currentAvailable = false;
    currentBlocked = false;
    externallyManaged = false;
    ensureProtectionSection();
    toggle.disabled = true;
    toggle.checked = false;
    stateLabel.textContent = copy.unavailable;
    stateLabel.classList.remove("is-blocked");
    message.classList.add("is-error");
    if (reason === "not-installed") {
      message.textContent = copy.missing;
    } else if (reason === "authentication") {
      message.textContent = copy.authentication;
    } else {
      message.textContent = copy.unreachable;
    }
    syncWarning();
  }

  async function load() {
    try {
      const response = await fetch("/aliases/sender-protection", {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.enabled) return;

      featureEnabled = true;
      if (!data.available) {
        unavailable(data.reason);
        return;
      }

      currentAvailable = true;
      ensureProtectionSection();
      externallyManaged = data.managed === false;
      message.classList.remove("is-error");
      setState(data.blocked);
      startCountdown(data.retry_after || 0);
    } catch (_error) {
      unavailable("unreachable");
    }
  }

  async function save() {
    if (externallyManaged) {
      setState(true);
      startCountdown(0);
      return;
    }

    const requested = toggle.checked;
    toggle.disabled = true;
    message.classList.remove("is-error");
    message.textContent = "";

    try {
      const response = await fetch("/aliases/sender-protection", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken(),
        },
        body: JSON.stringify({ blocked: requested }),
      });

      if (response.status === 409) {
        externallyManaged = true;
        currentAvailable = true;
        setState(true);
        startCountdown(0);
        return;
      }

      if (response.status === 429) {
        setState(currentBlocked);
        startCountdown(response.headers.get("Retry-After") || "1");
        return;
      }

      if (!response.ok) {
        setState(currentBlocked);
        toggle.disabled = false;
        message.classList.add("is-error");
        message.textContent = copy.failed;
        return;
      }

      const data = await response.json();
      currentAvailable = true;
      externallyManaged = data.managed === false;
      message.classList.remove("is-error");
      setState(data.blocked);
      startCountdown(data.retry_after || 0);
    } catch (_error) {
      setState(currentBlocked);
      toggle.disabled = false;
      message.classList.add("is-error");
      message.textContent = copy.failed;
    }
  }

  moveUsageSettings();
  void load();
})();
