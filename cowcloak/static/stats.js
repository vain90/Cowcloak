(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = {
    de: {
      senderTitle: "Absender",
      close: "Schließen",
      unexpectedFilter: "Nicht erwartet",
      unexpectedEmpty: "Keine Aliase mit nicht erwarteten Absendern.",
      unexpectedSummary: (count) => `${count} Alias${count === 1 ? "" : "e"} mit nicht erwarteten Absendern`,
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
      unexpectedFilter: "Unexpected",
      unexpectedEmpty: "No aliases with unexpected senders.",
      unexpectedSummary: (count) => `${count} alias${count === 1 ? "" : "es"} with unexpected senders`,
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
  let unexpectedFilterPill = null;
  let unexpectedGlobalCount = 0;
  let unexpectedRenderSequence = 0;
  const unexpectedCache = new Map();

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

  const enhanceSenderDetails = (root = document) => {
    root.querySelectorAll("details.sender-stats:not([data-sender-modalized])").forEach((details) => {
      details.dataset.senderModalized = "1";
      const summary = details.querySelector(":scope > summary");
      if (!summary) return;

      const hasUnexpected = Boolean(summary.querySelector(".sender-stats-alert"));
      const ownerRow = details.closest(".alias-row");
      if (hasUnexpected && ownerRow) ownerRow.classList.add("alias-row-unexpected");

      const trigger = document.createElement("button");
      trigger.className = `sender-stats-trigger${hasUnexpected ? " has-unexpected" : ""}`;
      trigger.type = "button";
      trigger.innerHTML = summary.innerHTML;
      trigger.setAttribute("aria-haspopup", "dialog");

      const dialog = document.createElement("dialog");
      dialog.className = "assign-dialog sender-stats-dialog";
      dialog.dataset.generatedSenderDialog = "1";
      dialog.id = `sender-stats-dialog-${++senderDialogCounter}`;
      trigger.setAttribute("aria-controls", dialog.id);

      const { head, close } = dialogHeading(text.senderTitle);
      const content = document.createElement("div");
      content.className = "sender-stats-dialog-content";

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

  const rowHasUnexpected = (row) => Boolean(row.querySelector(".sender-stats-alert"));

  const parseTotalPages = (documentRoot) => {
    const pages = [...documentRoot.querySelectorAll(".pagination .page-link")]
      .map((item) => Number.parseInt(item.textContent.trim(), 10))
      .filter(Number.isFinite);
    return pages.length ? Math.max(...pages) : 1;
  };

  const fetchAliasPage = async (page, query) => {
    const url = new URL("/aliases", window.location.origin);
    url.searchParams.set("status", "all");
    url.searchParams.set("per_page", "100");
    url.searchParams.set("page", String(page));
    if (query) url.searchParams.set("q", query);

    const response = await fetch(url, {
      headers: { "X-Cowcloak-Partial": "unexpected-filter" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`Unexpected-filter request failed with HTTP ${response.status}`);
    const html = await response.text();
    return new DOMParser().parseFromString(html, "text/html");
  };

  const loadUnexpectedRows = async (query = "") => {
    const cacheKey = query.trim().toLowerCase();
    if (unexpectedCache.has(cacheKey)) return unexpectedCache.get(cacheKey);

    const first = await fetchAliasPage(1, query);
    const totalPages = parseTotalPages(first);
    const documents = [first];
    if (totalPages > 1) {
      const rest = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, index) => fetchAliasPage(index + 2, query)),
      );
      documents.push(...rest);
    }

    const rows = documents.flatMap((doc) =>
      [...doc.querySelectorAll(".alias-row")]
        .filter(rowHasUnexpected)
        .map((row) => row.cloneNode(true)),
    );
    unexpectedCache.set(cacheKey, rows);
    return rows;
  };

  const isUnexpectedMode = () => window.location.hash === "#unexpected";

  const currentSearchQuery = () => document.querySelector("[data-live-search]")?.value.trim() || "";

  const unexpectedReturnTo = () => {
    const url = new URL(window.location.href);
    url.searchParams.set("status", "all");
    url.searchParams.delete("page");
    url.hash = "unexpected";
    return `${url.pathname}${url.search}${url.hash}`;
  };

  const setUnexpectedFilterVisualState = (active) => {
    document.querySelectorAll(".status-filters .filter-pill").forEach((pill) => {
      pill.classList.toggle("current", active ? pill === unexpectedFilterPill : false);
    });
  };

  const rebindInsertedAliasRows = (root) => {
    formatTimestamps(root);
    enhanceSenderDetails(root);
    window.bindCopyButtons?.(root);
    window.bindConfirmForms?.(root);
    window.bindReplacementActions?.(root);
  };

  const renderUnexpectedFilter = async () => {
    if (!isUnexpectedMode()) return;
    const sequence = ++unexpectedRenderSequence;
    const region = document.querySelector("[data-alias-results-region]");
    const aliasList = region?.querySelector(".alias-list");
    if (!region || !aliasList) return;

    setUnexpectedFilterVisualState(true);
    region.classList.add("unexpected-filter-active");
    const bulkToolbar = region.querySelector("[data-bulk-toolbar]");
    const footer = region.querySelector(".list-footer");
    if (bulkToolbar) bulkToolbar.hidden = true;
    if (footer) footer.hidden = true;

    aliasList.classList.add("unexpected-filter-loading");
    try {
      const query = currentSearchQuery();
      const rows = await loadUnexpectedRows(query);
      if (sequence !== unexpectedRenderSequence || !isUnexpectedMode()) return;

      document.querySelectorAll("[data-generated-sender-dialog]").forEach((dialog) => dialog.remove());
      aliasList.replaceChildren();

      if (rows.length) {
        rows.forEach((sourceRow) => {
          const row = document.importNode(sourceRow, true);
          row.querySelectorAll('input[name="return_to"]').forEach((input) => {
            input.value = unexpectedReturnTo();
          });
          aliasList.append(row);
        });
      } else {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = text.unexpectedEmpty;
        aliasList.append(empty);
      }

      const summary = document.querySelector("[data-assigned-summary]");
      if (summary) summary.textContent = text.unexpectedSummary(rows.length);
      rebindInsertedAliasRows(aliasList);
    } catch (error) {
      console.error("Could not load unexpected aliases", error);
    } finally {
      if (sequence === unexpectedRenderSequence) aliasList.classList.remove("unexpected-filter-loading");
    }
  };

  const installUnexpectedFilter = async () => {
    const filters = document.querySelector(".status-filters");
    if (!filters || filters.querySelector("[data-unexpected-filter]")) return;

    unexpectedFilterPill = document.createElement("a");
    unexpectedFilterPill.className = "filter-pill unexpected-filter-pill";
    unexpectedFilterPill.dataset.unexpectedFilter = "1";
    unexpectedFilterPill.href = "#unexpected";
    unexpectedFilterPill.append(document.createTextNode(`${text.unexpectedFilter} `));
    const count = document.createElement("span");
    count.textContent = "…";
    unexpectedFilterPill.append(count);
    filters.append(unexpectedFilterPill);

    unexpectedFilterPill.addEventListener("click", (event) => {
      event.preventDefault();
      const url = new URL(window.location.href);
      url.searchParams.set("status", "all");
      url.searchParams.delete("page");
      url.hash = "unexpected";
      history.pushState({}, "", url);
      renderUnexpectedFilter();
    });

    try {
      const rows = await loadUnexpectedRows("");
      unexpectedGlobalCount = rows.length;
      count.textContent = String(unexpectedGlobalCount);
      unexpectedFilterPill.classList.toggle("has-unexpected", unexpectedGlobalCount > 0);
    } catch (error) {
      console.error("Could not count unexpected aliases", error);
      const visibleCount = [...document.querySelectorAll(".alias-row")].filter(rowHasUnexpected).length;
      count.textContent = String(visibleCount);
      unexpectedFilterPill.classList.toggle("has-unexpected", visibleCount > 0);
    }

    if (isUnexpectedMode()) renderUnexpectedFilter();
  };

  const installUnexpectedSearchHandling = () => {
    const search = document.querySelector("[data-live-search]");
    if (!search || search.dataset.unexpectedSearchBound === "1") return;
    search.dataset.unexpectedSearchBound = "1";
    let timer = null;

    search.addEventListener(
      "input",
      (event) => {
        if (!isUnexpectedMode()) return;
        event.stopImmediatePropagation();
        clearTimeout(timer);
        timer = setTimeout(() => {
          const url = new URL(window.location.href);
          const query = search.value.trim();
          if (query) url.searchParams.set("q", query);
          else url.searchParams.delete("q");
          url.searchParams.set("status", "all");
          url.searchParams.delete("page");
          url.hash = "unexpected";
          history.replaceState({}, "", url);
          renderUnexpectedFilter();
        }, 180);
      },
      true,
    );
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

  const start = () => {
    formatTimestamps();
    enhanceSenderDetails();
    installUnexpectedSearchHandling();
    installUnexpectedFilter();
    buildUsedPoolPrompt();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches("[data-local-timestamp]")) formatTimestamp(node);
          formatTimestamps(node);
          enhanceSenderDetails(node);
          if (node.matches("[data-alias-results-region]") || node.querySelector("[data-alias-results-region]")) {
            unexpectedFilterPill = null;
            installUnexpectedSearchHandling();
            installUnexpectedFilter();
          }
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    window.addEventListener("popstate", () => {
      if (isUnexpectedMode()) renderUnexpectedFilter();
      else window.location.reload();
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
