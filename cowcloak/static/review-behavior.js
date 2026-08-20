(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = language === "de"
    ? { reviewAll: "Alle prüfen" }
    : { reviewAll: "Review all" };

  const LOGIN_PROMPT_PREFIX = "cowcloak-unexpected-review-login:";
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

  const unexpectedCount = () => {
    const value = document
      .querySelector("[data-unexpected-filter] > span")
      ?.textContent
      ?.trim();
    if (!value || value === "…") return null;
    const count = Number.parseInt(value, 10);
    return Number.isFinite(count) ? count : null;
  };

  const internalReviewTrigger = () =>
    document.querySelector("[data-unexpected-review-trigger]");

  const ensureReviewAction = () => {
    const filters = document.querySelector(".status-filters");
    const internal = internalReviewTrigger();
    if (!filters || !internal) return;

    internal.classList.add("unexpected-review-internal-trigger");

    let actions = document.querySelector("[data-unexpected-review-actions]");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "unexpected-review-actions";
      actions.dataset.unexpectedReviewActions = "1";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "button compact unexpected-review-all-button";
      button.dataset.unexpectedReviewAll = "1";
      button.textContent = text.reviewAll;
      button.addEventListener("click", () => internalReviewTrigger()?.click());
      actions.append(button);
      filters.insertAdjacentElement("beforebegin", actions);
    }

    const count = unexpectedCount();
    const button = actions.querySelector("[data-unexpected-review-all]");
    if (button) button.hidden = count === null || count < 1;

    if (loginPromptEvaluated || wasLoginPromptEvaluated() || count === null) return;
    if (document.querySelector("dialog[open]")) return;

    loginPromptEvaluated = true;
    markLoginPromptEvaluated();
    if (count > 0) internal.click();
  };

  const styleOfflineSenderDialogs = (root = document) => {
    const dialogs = [];
    if (root instanceof Element && root.matches("[data-review-pool-dialog]")) dialogs.push(root);
    root.querySelectorAll?.("[data-review-pool-dialog]").forEach((dialog) => dialogs.push(dialog));

    dialogs.forEach((dialog) => {
      dialog.querySelectorAll(".sender-stats-row").forEach((row) => {
        row.classList.add("unexpected");
      });
    });
  };

  const start = () => {
    if (!document.querySelector(".status-filters")) return;

    styleOfflineSenderDialogs();
    ensureReviewAction();

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node instanceof Element) styleOfflineSenderDialogs(node);
        });
      });
      ensureReviewAction();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    document.addEventListener("close", ensureReviewAction, true);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
