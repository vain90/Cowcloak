(() => {
  "use strict";

  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = language === "de"
    ? {
        actionRequired: "Handlungsbedarf",
        actionRequiredCount: (count) => `Handlungsbedarf (${count})`,
      }
    : {
        actionRequired: "Action required",
        actionRequiredCount: (count) => `Action required (${count})`,
      };

  let explicitQueryHandled = false;

  const ensureAliasAction = () => {
    const filters = document.querySelector(".status-filters");
    if (!filters) return null;

    let actions = document.querySelector("[data-unexpected-review-actions]");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "unexpected-review-actions action-required-actions";
      actions.dataset.unexpectedReviewActions = "1";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "button compact unexpected-review-all-button action-required-button";
      button.dataset.unexpectedReviewAll = "1";
      button.dataset.actionRequiredOpen = "1";
      button.textContent = text.actionRequired;
      actions.append(button);
      filters.insertAdjacentElement("beforebegin", actions);
    }
    return actions.querySelector("[data-action-required-open]");
  };

  const bindActionButtons = () => {
    document.querySelectorAll("[data-action-required-open]").forEach((button) => {
      if (button.dataset.actionRequiredBound === "1") return;
      button.dataset.actionRequiredBound = "1";
      button.addEventListener("click", async () => {
        if (!document.querySelector(".pool-item")) {
          window.location.assign("/offline-pool?action=required");
          return;
        }
        await window.MooliasActionRequired?.open();
      });
    });
  };

  const handleExplicitQuery = async (api) => {
    if (explicitQueryHandled || !api?.open) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "required") return;

    explicitQueryHandled = true;
    await api.open();
    params.delete("action");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  };

  const refresh = async () => {
    const aliasAction = ensureAliasAction();
    bindActionButtons();
    const api = window.MooliasActionRequired;
    if (!api) return;

    if (aliasAction && api.summary) {
      const summary = await api.summary();
      aliasAction.textContent = summary.total > 0
        ? text.actionRequiredCount(summary.total)
        : text.actionRequired;
      aliasAction.classList.toggle("has-action-required", summary.total > 0);
    }

    await handleExplicitQuery(api);
  };

  const start = () => {
    ensureAliasAction();
    bindActionButtons();
    refresh();

    const observer = new MutationObserver(() => {
      ensureAliasAction();
      bindActionButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("moolias:action-required-ready", refresh);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
