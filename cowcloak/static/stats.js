(() => {
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

  const start = () => {
    formatTimestamps();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches("[data-local-timestamp]")) formatTimestamp(node);
          formatTimestamps(node);
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
