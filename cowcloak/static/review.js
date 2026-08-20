(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = {
    de: {
      review: "Prüfen",
      title: "Unerwartete Absender prüfen",
      intro: (count) =>
        count === 1
          ? "Ein Alias enthält mindestens einen nicht erwarteten Absender. Prüfe hier die gesamte Absenderliste dieses Alias."
          : `${count} Aliase enthalten mindestens einen nicht erwarteten Absender. Prüfe hier pro Alias die gesamte Absenderliste.`,
      empty: "Aktuell gibt es keine Aliase mit nicht erwarteten Absendern.",
      unexpected: (count) => `${count} nicht erwartet`,
      close: "Schließen",
      senderTitle: "Absender",
      poolHint: "Dieser Offline-Alias ist noch nicht zugeordnet. Die Absenderbewertung steht nach der Zuordnung zur Verfügung.",
      pendingReview: "Noch nicht bewertet",
      loadFailed: "Die Liste der unerwarteten Absender konnte nicht geladen werden.",
    },
    en: {
      review: "Review",
      title: "Review unexpected senders",
      intro: (count) =>
        count === 1
          ? "One alias contains at least one unexpected sender. Review the complete sender list for that alias here."
          : `${count} aliases contain at least one unexpected sender. Review the complete sender list for each alias here.`,
      empty: "There are currently no aliases with unexpected senders.",
      unexpected: (count) => `${count} unexpected`,
      close: "Close",
      senderTitle: "Senders",
      poolHint: "This offline alias has not been assigned yet. Sender review becomes available after assignment.",
      pendingReview: "Not reviewed yet",
      loadFailed: "The unexpected sender list could not be loaded.",
    },
  }[language];

  const REOPEN_KEY = "cowcloak-unexpected-review-reopen";
  let reviewDialog = null;
  let reviewList = null;
  let reviewIntro = null;

  const handleAuthenticationLoss = (response) => {
    if (response.status !== 401) return false;
    window.location.assign("/");
    return true;
  };

  const parseTotalPages = (documentRoot) => {
    const pages = [...documentRoot.querySelectorAll(".pagination .page-link")]
      .map((item) => Number.parseInt(item.textContent.trim(), 10))
      .filter(Number.isFinite);
    return pages.length ? Math.max(...pages) : 1;
  };

  const fetchAliasPage = async (page) => {
    const url = new URL("/aliases", window.location.origin);
    url.searchParams.set("status", "unexpected");
    url.searchParams.set("per_page", "100");
    url.searchParams.set("page", String(page));

    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "X-Cowcloak-Partial": "unexpected-review",
      },
      credentials: "same-origin",
    });
    if (handleAuthenticationLoss(response)) throw new Error("Authentication required");
    if (!response.ok) throw new Error(`Unexpected review request failed with HTTP ${response.status}`);
    return new DOMParser().parseFromString(await response.text(), "text/html");
  };

  const loadUnexpectedRows = async () => {
    const first = await fetchAliasPage(1);
    const documents = [first];
    const totalPages = parseTotalPages(first);
    if (totalPages > 1) {
      const rest = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, index) => fetchAliasPage(index + 2)),
      );
      documents.push(...rest);
    }

    return documents.flatMap((documentRoot) =>
      [...documentRoot.querySelectorAll(".alias-row")].map((row) => row.cloneNode(true)),
    );
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

  const bindDialogClose = (dialog, close) => {
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  };

  const ensureReviewDialog = () => {
    if (reviewDialog?.isConnected) return reviewDialog;

    reviewDialog = document.createElement("dialog");
    reviewDialog.className = "assign-dialog unexpected-review-dialog";
    reviewDialog.dataset.unexpectedReviewDialog = "1";

    const { head, close } = dialogHeading(text.title);
    reviewIntro = document.createElement("p");
    reviewIntro.className = "muted unexpected-review-intro";
    reviewList = document.createElement("div");
    reviewList.className = "unexpected-review-list";

    reviewDialog.append(head, reviewIntro, reviewList);
    document.body.append(reviewDialog);
    bindDialogClose(reviewDialog, close);
    return reviewDialog;
  };

  const prepareReviewForm = (form) => {
    const returnTo = form.querySelector('input[name="return_to"]');
    if (returnTo) returnTo.value = "/aliases";
    form.addEventListener("submit", () => {
      try {
        sessionStorage.setItem(REOPEN_KEY, "1");
      } catch (error) {
        console.debug("sessionStorage is unavailable", error);
      }
    });
  };

  const buildAliasReview = (sourceRow) => {
    const select = sourceRow.querySelector("[data-alias-select]");
    const address = select?.dataset.address?.trim() || "";
    const description = select?.dataset.description?.trim() || "";
    const senderDetails = sourceRow.querySelector("details.sender-stats");
    const sourceList = senderDetails?.querySelector(".sender-stats-list");
    if (!address || !sourceList) return null;

    const unexpectedCount = sourceList.querySelectorAll(".sender-stats-row.unexpected").length;
    const section = document.createElement("section");
    section.className = "unexpected-review-alias";

    const header = document.createElement("div");
    header.className = "unexpected-review-alias-head";
    const identity = document.createElement("div");
    identity.className = "unexpected-review-identity";
    if (description) {
      const strong = document.createElement("strong");
      strong.textContent = description;
      identity.append(strong);
    }
    const code = document.createElement("code");
    code.textContent = address;
    identity.append(code);

    const alert = document.createElement("span");
    alert.className = "sender-stats-alert";
    alert.textContent = text.unexpected(unexpectedCount);
    header.append(identity, alert);

    const senderList = document.importNode(sourceList, true);
    senderList.querySelectorAll(".sender-review-form").forEach(prepareReviewForm);
    section.append(header, senderList);

    const footnote = senderDetails.querySelector(".sender-stats-footnote")?.cloneNode(true);
    if (footnote) section.append(footnote);
    return section;
  };

  const renderReviewDialog = async () => {
    ensureReviewDialog();
    reviewList.replaceChildren();
    reviewIntro.textContent = "…";

    try {
      const rows = await loadUnexpectedRows();
      reviewIntro.textContent = text.intro(rows.length);
      rows.forEach((row) => {
        const section = buildAliasReview(row);
        if (section) reviewList.append(section);
      });
      if (!reviewList.children.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = text.empty;
        reviewList.append(empty);
      }
      return rows.length;
    } catch (error) {
      console.error("Could not load unexpected sender review", error);
      reviewIntro.textContent = text.loadFailed;
      return 0;
    }
  };

  const openReviewDialog = async () => {
    const dialog = ensureReviewDialog();
    await renderReviewDialog();
    if (!dialog.open) dialog.showModal();
  };

  const syncReviewTrigger = () => {
    const filters = document.querySelector(".status-filters");
    const pill = filters?.querySelector("[data-unexpected-filter]");
    if (!filters || !pill) return;

    let trigger = filters.querySelector("[data-unexpected-review-trigger]");
    if (!trigger) {
      trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "filter-pill unexpected-review-trigger";
      trigger.dataset.unexpectedReviewTrigger = "1";
      trigger.textContent = text.review;
      trigger.addEventListener("click", openReviewDialog);
      pill.insertAdjacentElement("afterend", trigger);
    }

    const count = Number.parseInt(pill.querySelector("span")?.textContent || "", 10);
    trigger.hidden = !Number.isFinite(count) || count < 1;
  };

  const buildPoolSenderDialog = (trigger) => {
    const item = trigger.closest(".pool-item");
    const assignButton = item?.querySelector("[data-open-assign-dialog]");
    const aliasId = assignButton?.dataset.openAssignDialog;
    const address = item?.querySelector("[data-pool-address]")?.textContent.trim();
    if (!aliasId || !address) return null;

    let dialog = document.querySelector(`[data-review-pool-dialog="${CSS.escape(aliasId)}"]`);
    if (dialog) return dialog;

    const sourceDialog = document.querySelector(`[data-assign-dialog="${CSS.escape(aliasId)}"]`);
    const sourceList = sourceDialog?.querySelector(".pool-assignment-usage .sender-stats-list");
    if (!sourceList) return null;

    dialog = document.createElement("dialog");
    dialog.className = "assign-dialog sender-stats-dialog";
    dialog.dataset.reviewPoolDialog = aliasId;
    const { head, close } = dialogHeading(text.senderTitle);
    const content = document.createElement("div");
    content.className = "sender-stats-dialog-content";

    const context = document.createElement("div");
    context.className = "sender-review-settings";
    const code = document.createElement("code");
    code.textContent = address;
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = text.poolHint;
    context.append(code, hint);

    const list = document.importNode(sourceList, true);
    list.classList.remove("pool-sender-list");
    list.querySelectorAll(".sender-stats-row").forEach((row) => {
      if (row.querySelector(".sender-review-state")) return;
      const state = document.createElement("span");
      state.className = "sender-review-state";
      state.textContent = text.pendingReview;
      const count = row.querySelector(".sender-message-count");
      if (count) row.insertBefore(state, count);
      else row.append(state);
    });

    content.append(context, list);
    dialog.append(head, content);
    document.body.append(dialog);
    bindDialogClose(dialog, close);
    return dialog;
  };

  const installPoolSenderCapture = () => {
    document.addEventListener(
      "click",
      (event) => {
        const trigger = event.target.closest?.(".pool-item .sender-stats-trigger");
        if (!trigger) return;
        const dialog = buildPoolSenderDialog(trigger);
        if (!dialog) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        dialog.showModal();
      },
      true,
    );
  };

  const start = () => {
    if (!document.querySelector(".status-filters")) return;
    installPoolSenderCapture();
    syncReviewTrigger();

    const observer = new MutationObserver(() => syncReviewTrigger());
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    try {
      if (sessionStorage.getItem(REOPEN_KEY) === "1") {
        sessionStorage.removeItem(REOPEN_KEY);
        openReviewDialog();
      }
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
