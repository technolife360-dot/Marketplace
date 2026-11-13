(() => {
  "use strict";

  const panel = document.createElement("section");
  panel.id = "notification-panel";
  panel.className = "notification-panel";
  panel.hidden = true;
  panel.tabIndex = -1;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-labelledby", "notification-panel-title");
  document.body.append(panel);

  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (character) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
  );
  const icon = (name) => `<svg class="notification-panel-glyph" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  let openPanel;

  function position() {
    if (!openPanel) return;
    const { trigger } = openPanel;
    const bounds = trigger.getBoundingClientRect();
    if (!bounds.width || bounds.bottom <= 0 || bounds.top >= innerHeight) {
      close();
      return;
    }
    const gutter = innerWidth <= 600 ? 10 : 16;
    const viewportWidth = document.documentElement.clientWidth;
    const width = Math.min(448, viewportWidth - gutter * 2);
    const top = Math.max(gutter, bounds.bottom + 8);
    const left = Math.max(gutter, Math.min(bounds.right - width, viewportWidth - width - gutter));
    panel.style.width = `${width}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.maxHeight = `${Math.max(0, Math.min(580, innerHeight - top - gutter))}px`;
  }

  function close(restoreFocus = false) {
    if (!openPanel) return;
    const { trigger, request } = openPanel;
    openPanel = null;
    request?.abort();
    panel.hidden = true;
    panel.replaceChildren();
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus({ preventScroll: true });
  }

  function render(state, items) {
    const { copy, allHref, settingsHref, guest, list, markAll } = state;
    const busy = items === undefined;
    const error = items === null;
    const focused = panel.contains(document.activeElement);
    const showMarkAll = markAll && items?.some((item) => item.unread);
    panel.innerHTML = `
      <header class="notification-panel-header">
        <h2 id="notification-panel-title">${escape(copy.title)}</h2>
        <div class="notification-panel-actions">
          ${showMarkAll ? `<button type="button" data-notification-mark-all aria-label="${escape(copy.markAll)}" title="${escape(copy.markAll)}">${icon("check")}</button>` : ""}
          ${!guest ? `<a href="${escape(settingsHref)}" aria-label="${escape(copy.settings)}" title="${escape(copy.settings)}">${icon("settings")}</a>` : ""}
        </div>
      </header>
      <div class="notification-panel-scroll" aria-busy="${busy}">
        ${items?.length ? `<ul class="notification-panel-list">${items.map((item) => `
          <li><a class="notification-panel-row${item.unread ? " is-unread" : ""}" href="${escape(item.href)}" data-notification-row="${escape(item.id)}">
            <span class="notification-panel-avatar" aria-hidden="true">${item.avatar || icon(item.icon || "bell")}</span>
            <span class="notification-panel-copy">
              <strong>${escape(item.title)}</strong>
              ${item.body ? `<span>${escape(item.body)}</span>` : ""}
              ${item.time ? `<time datetime="${escape(item.datetime)}" title="${escape(item.fullTime)}">${escape(item.time)}</time>` : ""}
              ${item.unread ? `<span class="notification-panel-sr">${escape(copy.unread)}</span>` : ""}
            </span>
        </a></li>`).join("")}</ul>` : `<div class="notification-panel-state">
          <span class="notification-panel-state-icon" aria-hidden="true"${busy ? ' data-loading' : ""}>${busy ? "" : icon(error ? "info" : "bell")}</span>
          <p role="status">${escape(busy ? copy.loading : error ? copy.error : guest ? guest.message : copy.empty)}</p>
          ${error ? `<button type="button" data-notification-retry>${escape(copy.retry)}</button>` : ""}
          ${guest ? `<a href="${escape(guest.href)}">${escape(guest.label)}</a>` : ""}
        </div>`}
      </div>
      ${!guest && list ? `<footer class="notification-panel-footer"><a href="${escape(allHref)}">${escape(copy.viewAll)} ${icon("arrow-right")}</a></footer>` : ""}`;
    if (focused && !panel.contains(document.activeElement)) panel.focus({ preventScroll: true });
  }

  async function load(state) {
    state.request?.abort();
    const request = new AbortController();
    state.request = request;
    try {
      const items = state.list ? await state.list(request.signal) : [];
      if (openPanel !== state || request.signal.aborted) return;
      state.items = items;
      render(state, items);
    } catch {
      if (openPanel !== state || request.signal.aborted) return;
      render(state, null);
    }
  }

  function bind(trigger, options) {
    trigger.setAttribute("aria-controls", panel.id);
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    trigger.addEventListener("click", () => {
      if (openPanel?.trigger === trigger) {
        close(true);
        return;
      }
      close();
      const state = { ...options(), trigger };
      openPanel = state;
      render(state, state.guest ? [] : undefined);
      panel.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      position();
      if (panel.hidden) return;
      panel.focus({ preventScroll: true });
      if (!state.guest) void load(state);
    });
  }

  panel.addEventListener("click", async (event) => {
    const state = openPanel;
    if (!state) return;
    const retry = event.target.closest("[data-notification-retry]");
    const mark = event.target.closest("[data-notification-mark-all]");
    if (retry || mark) {
      const button = retry || mark;
      if (button.disabled) return;
      button.disabled = true;
      panel.focus({ preventScroll: true });
      if (mark) {
        try {
          await state.markAll();
        } catch (error) {
          if (openPanel === state) {
            button.disabled = false;
            button.focus({ preventScroll: true });
            state.onError(error);
          }
          return;
        }
      }
      if (openPanel === state) await load(state);
      return;
    }
    const link = event.target.closest("a[href]");
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const item = state.items?.find((entry) => entry.id === link.dataset.notificationRow);
    if (item?.unread && state.openItem && (state.canOpenItem?.() ?? true)) {
      event.preventDefault();
      state.openItem(item);
    }
    // Keep the link connected until delegated navigation handlers have run.
    setTimeout(() => { if (openPanel === state) close(); }, 0);
  });

  document.addEventListener("pointerdown", (event) => {
    if (openPanel && !panel.contains(event.target) && !openPanel.trigger.contains(event.target)) close();
  });
  document.addEventListener("focusin", (event) => {
    if (openPanel && !panel.contains(event.target) && !openPanel.trigger.contains(event.target)) close();
  });
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") {
      const controls = [...panel.querySelectorAll("a[href], button:not(:disabled)")];
      if (!controls.length || (event.shiftKey && (event.target === panel || event.target === controls[0])) || (!event.shiftKey && event.target === controls.at(-1))) {
        event.preventDefault();
        close(true);
      }
    }
  });
  window.addEventListener("resize", position);
  window.addEventListener("scroll", position, { passive: true });
  window.addEventListener("hashchange", () => close());
  window.addEventListener("popstate", () => close());

  function timestamp(datetime, language) {
    const source = String(datetime ?? "").trim().replace(" ", "T").replace(/([+-]\d{2})$/, "$1:00");
    const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(source) ? source : source + "Z");
    if (!Number.isFinite(date.getTime())) return {};
    const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
    const relative = new Intl.RelativeTimeFormat(language, { numeric: "auto", style: "short" });
    const time = minutes < 60 ? relative.format(-minutes, "minute") : minutes < 1440 ? relative.format(-Math.floor(minutes / 60), "hour") : minutes < 10080 ? relative.format(-Math.floor(minutes / 1440), "day") : date.toLocaleDateString(language, { dateStyle: "medium" });
    return { time, datetime: date.toISOString(), fullTime: date.toLocaleString(language) };
  }

  window.NotificationPanel = { bind, close, timestamp };
})();
