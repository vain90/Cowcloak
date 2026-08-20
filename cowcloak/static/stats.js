(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = {
    de: {
      senderTitle: "Absender",
      close: "Schließen",
      ignoreUnexpected: "Unerwartete Absender für diesen Alias ignorieren",
      ignoreUnexpectedHint: "Absender und Statistiken bleiben sichtbar, aber dieser Alias wird nicht mehr als unerwartet gemeldet und zählt nicht im roten Filter.",
      ignoreUnexpectedMuted: "Prüfung aus",
      ignoreUnexpectedFailed: "Die Einstellung für unerwartete Absender konnte nicht gespeichert werden.",
      poolTitle: "Offline-Aliase wurden benutzt",
      poolIntro: (count) =>
        count === 1
          ? "Für einen noch nicht zugeordneten Offline-Alias ist eine Mail eingegangen. Du kannst ihn jetzt direkt zuordnen."
          : `Für ${count} noch nicht zugeordnete Offline-Aliase sind Mails eingegangen. Du kannst sie jetzt gesammelt zuordnen.`,
      poolPrivacyHint: "Angezeigt werden die Absenderinformationen, die dein aktueller Statistikmodus speichern darf.",
      poolAssign: "Ausgewählte zuordnen",
      poolLater: "Später",
      poolPurpose: "Name / Zweck",
      poolPurposePlaceholder: "z. B. Hotel, Shop, Newsletter …",
      poolSelected: "Jetzt zuordnen",
      poolSkipped: "Vorerst nicht zuordnen",
      poolMissingPurpose: "Bitte trage für jeden ausgewählten Alias einen Namen oder Zweck ein.",
      poolFailed: "Mindestens ein Offline-Alias konnte nicht zugeordnet werden. Die Ansicht wird neu geladen, damit du den aktuellen Stand siehst.",
    },
    en: {
      senderTitle: "Senders",
      close: "Close",
      ignoreUnexpected: "Ignore unexpected senders for this alias",
      ignoreUnexpectedHint: "Sender details and statistics stay visible, but this alias is no longer flagged as unexpected and is excluded from the red filter.",
      ignoreUnexpectedMuted: "Review off",
      ignoreUnexpectedFailed: "The unexpected-sender setting could not be saved.",
      poolTitle: "Offline aliases were used",
      poolIntro: (count) =>
        count === 1
          ? "Mail was received by one unassigned offline alias. You can assign it now."
          : `Mail was received by ${count} unassigned offline aliases. You can assign them together now.`,
      poolPrivacyHint: "The sender information shown is limited to what your current statistics mode is allowed to store.",
      poolAssign: "Assign selected",
      poolLater: "Later",
      poolPurpose: "Name / purpose",
      poolPurposePlaceholder: "e.g. hotel, shop, newsletter …",
      poolSelected: "Assign now",
      poolSkipped: "Leave unassigned for now",
      poolMissingPurpose: "Enter a name or purpose for every selected alias.",
      poolFailed: "At least one offline alias could not be assigned. The page will reload so you can see the current state.",
    },
  }[language];

  let senderDialogCounter = 0;
  const ignoredUnexpectedAliases = new Set();

  const formatTimestamp = (element) => {
    if (element.dataset.localTimestampFormatted === "1") return;

    const seconds = Number(element.dataset.localTimestamp);
    if (!Number.isFinite(seconds)) return;

    const date = new Date(seconds * 1000);
    if (Number.isNaN(date.getTime())) return;

    const locale = document.documentElement.lang || undefined;
    const formatter = new Intl.DateTimeFormat(locale, {
      dateStyle: "short",
      timeStyle: "short",
    });

    element.textContent = formatter.format(date);
    element.dateTime = date.toISOString();
    element.dataset.localTimestampFormatted = "1";
  };

  const formatTimestamps = (root = document) => {
    root.querySelectorAll("[data-local-timestamp]").forEach(formatTimestamp);
  };

  const dialogHeading = (title) => {
    const head = document.createElement("div");
    head.className = "dialog-head";

    const heading = document.createElement("h2");
    heading.textContent = title;

    const close = document.createElement("button");
    close.className = "dialog-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", text.close);
    close.title = text.close;

    head.append(heading, close);
    return { head, close };
  };

  const bindDialogClose = (dialog, closeButton) => {
    closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  };

  const rowAlias = (row) => {
    const checkbox = row?.querySelector("[data-alias-select]");
    const address = checkbox?.dataset.address?.trim().toLowerCase() || "";
    return {
      id: checkbox?.value || "",
      address,
    };
  };

  const isUnexpectedIgnored = (row) => {
    const { address } = rowAlias(row);
    return Boolean(address && ignoredUnexpectedAliases.has(address));
  };

  const loadReviewSettings = async () => {
    if (!document.querySelector(".status-filters")) return;
    try {
      const response = await fetch("/aliases/review-settings", {
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const payload = await response.json();
      const ignored = Array.isArray(payload.ignored_unexpected)
        ? payload.ignored_unexpected
        : [];
      ignoredUnexpectedAliases.clear();
      ignored.forEach((address) => {
        const normalized = String(address || "").trim().toLowerCase();
        if (normalized) ignoredUnexpectedAliases.add(normalized);
      });
    } catch (error) {
      console.error("Could not load alias review settings", error);
    }
  };

  const saveUnexpectedIgnored = async (row, ignored) => {
    const { id, address } = rowAlias(row);
    const csrf = document.querySelector('input[name="csrf_token"]')?.value;
    if (!id || !address || !csrf) throw new Error("Missing alias review setting context");

    const form = new FormData();
    form.append("csrf_token", csrf);
    if (ignored) form.append("ignored", "true");

    const response = await fetch(`/aliases/${encodeURIComponent(id)}/unexpected-monitoring`, {
      method: "POST",
      body: form,
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error(`Unexpected monitoring update failed with HTTP ${response.status}`);
    }
  };

  const buildUnexpectedSetting = (ownerRow, ignored) => {
    const wrapper = document.createElement("div");
    wrapper.className = "sender-review-settings";

    const label = document.createElement("label");
    label.className = "check-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = ignored;
    const labelText = document.createElement("span");
    labelText.textContent = text.ignoreUnexpected;
    label.append(checkbox, labelText);

    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = text.ignoreUnexpectedHint;

    checkbox.addEventListener("change", async () => {
      checkbox.disabled = true;
      try {
        await saveUnexpectedIgnored(ownerRow, checkbox.checked);
        window.location.reload();
      } catch (error) {
        console.error("Could not save unexpected sender setting", error);
        checkbox.checked = !checkbox.checked;
        checkbox.disabled = false;
        window.alert(text.ignoreUnexpectedFailed);
      }
    });

    wrapper.append(label, hint);
    return wrapper;
  };

  const enhanceSenderDetails = (root = document) => {
    root.querySelectorAll("details.sender-stats:not([data-sender-modalized])").forEach((details) => {
      details.dataset.senderModalized = "1";
      const summary = details.querySelector(":scope > summary");
      if (!summary) return;

      const ownerRow = details.closest(".alias-row");
      const ignored = Boolean(ownerRow && isUnexpectedIgnored(ownerRow));
      const rawUnexpected = Boolean(summary.querySelector(".sender-stats-alert"));
      const hasUnexpected = rawUnexpected && !ignored;
      if (hasUnexpected && ownerRow) ownerRow.classList.add("alias-row-unexpected");
      else ownerRow?.classList.remove("alias-row-unexpected");

      const trigger = document.createElement("button");
      trigger.className = `sender-stats-trigger${hasUnexpected ? " has-unexpected" : ""}`;
      trigger.type = "button";
      trigger.innerHTML = summary.innerHTML;
      trigger.setAttribute("aria-haspopup", "dialog");
      if (ignored) {
        trigger.querySelector(".sender-stats-alert")?.remove();
        const muted = document.createElement("span");
        muted.className = "sender-stats-count sender-review-muted";
        muted.textContent = text.ignoreUnexpectedMuted;
        trigger.append(muted);
      }

      const dialog = document.createElement("dialog");
      dialog.className = "assign-dialog sender-stats-dialog";
      dialog.dataset.generatedSenderDialog = "1";
      dialog.id = `sender-stats-dialog-${++senderDialogCounter}`;
      trigger.setAttribute("aria-controls", dialog.id);

      const { head, close } = dialogHeading(text.senderTitle);
      const content = document.createElement("div");
      content.className = "sender-stats-dialog-content";

      if (ownerRow) content.append(buildUnexpectedSetting(ownerRow, ignored));
      [...details.children].forEach((child) => {
        if (child !== summary) content.append(child);
      });

      dialog.append(head, content);
      document.body.append(dialog);
      details.replaceWith(trigger);

      trigger.addEventListener("click", () => dialog.showModal());
      bindDialogClose(dialog, close);
    });
  };

  const promptStorageKey = () => {
    const csrf = document.querySelector('input[name="csrf_token"]')?.value;
    return csrf ? `cowcloak-used-pool-prompt:${csrf}` : null;
  };

  const wasPoolPromptSeen = (key) => {
    if (!key) return false;
    try {
      return sessionStorage.getItem(key) === "1";
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
      return false;
    }
  };

  const markPoolPromptSeen = (key) => {
    if (!key) return;
    try {
      sessionStorage.setItem(key, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const buildUsedPoolPrompt = () => {
    const usedItems = [...document.querySelectorAll(".pool-item.pool-item-used")];
    if (!usedItems.length) return;

    const storageKey = promptStorageKey();
    if (wasPoolPromptSeen(storageKey)) return;

    const dialog = document.createElement("dialog");
    dialog.className = "assign-dialog used-pool-dialog";
    dialog.dataset.usedPoolPrompt = "1";

    const { head, close } = dialogHeading(text.poolTitle);
    const intro = document.createElement("p");
    intro.className = "muted used-pool-intro";
    intro.textContent = text.poolIntro(usedItems.length);

    const privacy = document.createElement("p");
    privacy.className = "hint used-pool-privacy";
    privacy.textContent = text.poolPrivacyHint;

    const form = document.createElement("form");
    form.className = "stack used-pool-form";

    const list = document.createElement("div");
    list.className = "used-pool-list";

    usedItems.forEach((item) => {
      const assignButton = item.querySelector("[data-open-assign-dialog]");
      const aliasId = assignButton?.dataset.openAssignDialog;
      const address = item.querySelector("[data-pool-address]")?.textContent.trim();
      const sourceDialog = aliasId
        ? document.querySelector(`[data-assign-dialog="${CSS.escape(aliasId)}"]`)
        : null;
      if (!aliasId || !address || !sourceDialog) return;

      const row = document.createElement("section");
      row.className = "used-pool-row";
      row.dataset.poolAliasId = aliasId;

      const selectLabel = document.createElement("label");
      selectLabel.className = "used-pool-select check-row";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      const selectText = document.createElement("span");
      selectText.textContent = text.poolSelected;
      selectLabel.append(checkbox, selectText);

      const identity = document.createElement("div");
      identity.className = "used-pool-identity";
      const code = document.createElement("code");
      code.textContent = address;
      identity.append(code);

      const usage = sourceDialog.querySelector(".pool-assignment-usage")?.cloneNode(true);
      if (usage) identity.append(usage);

      const purposeLabel = document.createElement("label");
      purposeLabel.className = "used-pool-purpose";
      const purposeText = document.createElement("span");
      purposeText.textContent = text.poolPurpose;
      const purpose = document.createElement("input");
      purpose.type = "text";
      purpose.maxLength = 160;
      purpose.required = true;
      purpose.placeholder = text.poolPurposePlaceholder;
      purpose.autocomplete = "off";
      purposeLabel.append(purposeText, purpose);

      const syncSelection = () => {
        purpose.disabled = !checkbox.checked;
        purpose.required = checkbox.checked;
        row.classList.toggle("skipped", !checkbox.checked);
        selectText.textContent = checkbox.checked ? text.poolSelected : text.poolSkipped;
      };
      checkbox.addEventListener("change", syncSelection);
      syncSelection();

      row.append(selectLabel, identity, purposeLabel);
      list.append(row);
    });

    if (!list.children.length) return;

    const actions = document.createElement("div");
    actions.className = "button-row used-pool-actions";
    const assign = document.createElement("button");
    assign.className = "button primary";
    assign.type = "submit";
    assign.textContent = text.poolAssign;
    const later = document.createElement("button");
    later.className = "button";
    later.type = "button";
    later.textContent = text.poolLater;
    actions.append(assign, later);

    form.append(list, actions);
    dialog.append(head, intro, privacy, form);
    document.body.append(dialog);
    formatTimestamps(dialog);

    close.addEventListener("click", () => dialog.close());
    later.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => markPoolPromptSeen(storageKey));

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selected = [...list.querySelectorAll(".used-pool-row")].filter(
        (row) => row.querySelector('input[type="checkbox"]')?.checked,
      );
      if (!selected.length) {
        dialog.close();
        return;
      }

      for (const row of selected) {
        const purpose = row.querySelector('.used-pool-purpose input');
        if (!purpose?.value.trim()) {
          window.alert(text.poolMissingPurpose);
          purpose?.focus();
          return;
        }
      }

      assign.disabled = true;
      later.disabled = true;
      let failed = false;
      for (const row of selected) {
        const aliasId = row.dataset.poolAliasId;
        const purpose = row.querySelector('.used-pool-purpose input');
        const sourceForm = document.querySelector(
          `[data-assign-dialog="${CSS.escape(aliasId)}"] form`,
        );
        if (!sourceForm || !purpose) {
          failed = true;
          break;
        }

        const data = new FormData();
        const csrf = sourceForm.querySelector('input[name="csrf_token"]')?.value;
        if (!csrf) {
          failed = true;
          break;
        }
        data.append("csrf_token", csrf);
        data.append("description", purpose.value.trim());

        try {
          const response = await fetch(sourceForm.action, {
            method: "POST",
            body: data,
            credentials: "same-origin",
          });
          if (!response.ok) {
            failed = true;
            break;
          }
        } catch (error) {
          console.error("Offline alias assignment failed", error);
          failed = true;
          break;
        }
      }

      markPoolPromptSeen(storageKey);
      if (failed) window.alert(text.poolFailed);
      window.location.reload();
    });

    dialog.showModal();
    dialog.querySelector('.used-pool-purpose input:not(:disabled)')?.focus();
  };

  const start = async () => {
    await loadReviewSettings();
    formatTimestamps();
    enhanceSenderDetails();
    buildUsedPoolPrompt();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches("[data-local-timestamp]")) formatTimestamp(node);
          formatTimestamps(node);
          enhanceSenderDetails(node);
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
