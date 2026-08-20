(() => {
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

  const LOGIN_PROMPT_PREFIX = "cowcloak-action-required-login:";
  let loginPromptEvaluated = false;

  const csrfToken = () => document.querySelector('input[name="csrf_token"]')?.value || "";

  const loginPromptKey = () => {
    const csrf = csrfToken();
    return csrf ? `${LOGIN_PROMPT_PREFIX}${csrf}` : null;
  };

  const wasLoginPromptEvaluated = () => {
    const key = loginPromptKey();
    if (!key) return true;
    try {
      return sessionStorage.getItem(key) === "1";
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
      return true;
    }
  };

  const markLoginPromptEvaluated = () => {
    const key = loginPromptKey();
    if (!key) return;
    try {
      sessionStorage.setItem(key, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const hasBlockingDialog = () =>
    Boolean(document.querySelector("dialog[open]:not([data-action-required-dialog])"));

  const ensureAction = () => {
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
      button.addEventListener("click", () => window.CowcloakActionRequired?.open());
      actions.append(button);
      filters.insertAdjacentElement("beforebegin", actions);
    }
    return actions.querySelector("[data-action-required-open]");
  };

  const refresh = async () => {
    const action = ensureAction();
    const api = window.CowcloakActionRequired;
    if (!action || !api?.summary) return;

    const summary = await api.summary();
    action.textContent = summary.total > 0
      ? text.actionRequiredCount(summary.total)
      : text.actionRequired;
    action.classList.toggle("has-action-required", summary.total > 0);

    if (loginPromptEvaluated || wasLoginPromptEvaluated()) return;
    if (hasBlockingDialog()) return;

    loginPromptEvaluated = true;
    markLoginPromptEvaluated();
    if (summary.total > 0) await api.open();
  };

  const start = () => {
    if (!document.querySelector(".status-filters")) return;
    ensureAction();
    refresh();

    const observer = new MutationObserver(() => ensureAction());
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });

    document.addEventListener("close", () => {
      if (!loginPromptEvaluated && !wasLoginPromptEvaluated()) refresh();
    }, true);
    document.addEventListener("cowcloak:action-required-ready", refresh);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
