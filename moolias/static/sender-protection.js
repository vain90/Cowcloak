(() => {
  const path = window.location.pathname;
  if (path !== "/aliases") return;

  const topbar = document.querySelector(".topbar");
  if (!topbar) return;

  const language = document.documentElement.lang === "de" ? "de" : "en";
  const copy = {
    de: {
      title: "Primäradresse schützen",
      description:
        "Verhindert, dass deine eigentliche Mailbox-Adresse als Absender verwendet wird. Der Empfang bleibt unverändert.",
      toggle: "Primäradresse als Absender sperren",
      blocked: "Geschützt",
      allowed: "Senden erlaubt",
      external: "Extern geschützt",
      externalHint:
        "Diese Adresse wird bereits durch eine bestehende Mailcow/Postfix-Regel gesperrt und deshalb nicht von Moolias verwaltet.",
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
      title: "Protect primary address",
      description:
        "Prevents your real mailbox address from being used as a sender. Receiving mail is unchanged.",
      toggle: "Block primary address as sender",
      blocked: "Protected",
      allowed: "Sending allowed",
      external: "Protected externally",
      externalHint:
        "This address is already blocked by an existing Mailcow/Postfix rule and is therefore not managed by Moolias.",
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

  let card = null;
  let toggle = null;
  let stateLabel = null;
  let message = null;
  let currentBlocked = false;
  let externallyManaged = false;
  let countdownTimer = null;

  function csrfToken() {
    return document.querySelector('form[action="/logout"] input[name="csrf_token"]')?.value || "";
  }

  function ensureCard() {
    if (card) return card;

    card = document.createElement("section");
    card.className = "card sender-protection-card top-gap";
    card.innerHTML = `
      <div class="sender-protection-copy">
        <div class="sender-protection-title-row">
          <h2>${copy.title}</h2>
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

    topbar.insertAdjacentElement("afterend", card);
    toggle = card.querySelector('input[type="checkbox"]');
    stateLabel = card.querySelector(".sender-protection-state");
    message = card.querySelector(".sender-protection-message");
    toggle.addEventListener("change", save);
    return card;
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
    ensureCard();
    toggle.disabled = true;
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
  }

  async function load() {
    try {
      const response = await fetch("/aliases/sender-protection", {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.enabled) return;
      if (!data.available) {
        unavailable(data.reason);
        return;
      }

      ensureCard();
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

  load();
})();
