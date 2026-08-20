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
    },
    en: {
      senderTitle: "Senders",
      close: "Close",
      ignoreUnexpected: "Ignore unexpected senders for this alias",
      ignoreUnexpectedHint: "Sender details and statistics stay visible, but this alias is no longer flagged as unexpected and is excluded from the red filter.",
      ignoreUnexpectedMuted: "Review off",
      ignoreUnexpectedFailed: "The unexpected-sender setting could not be saved.",
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
        await window.CowcloakDialog.error(text.ignoreUnexpectedFailed);
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

  const start = async () => {
    await loadReviewSettings();
    formatTimestamps();
    enhanceSenderDetails();

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
