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
    const { copy, settingsHref, guest, markAll } = state;
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
      </div>`;
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

  function open(trigger, options) {
    if (!trigger || openPanel?.trigger === trigger) return;
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
  }

  function bind(trigger, options) {
    trigger.setAttribute("aria-controls", panel.id);
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    trigger.addEventListener("click", () => {
      if (openPanel?.trigger === trigger) close(true);
      else open(trigger, options);
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

  function translate(key, language, values = {}) {
    const data = window.SENTRYLOOT_LANGUAGE_DATA;
    const template = data?.notificationMessages?.[language]?.[key] ?? data?.messages?.[language]?.[key] ?? key;
    return template.replace(/\{(\w+)\}/g, (token, name) => values[name] ?? token);
  }

  function copy(language) {
    const t = (key) => translate(key, language);
    return {
      title: t("Notifications"),
      settings: t("Notification settings"),
      markAll: t("Mark all as read"),
      empty: t("No notifications yet."),
      error: t("Could not load notifications."),
      retry: t("Try again"),
      loading: t("Loading…"),
      unread: t("Unread"),
    };
  }

  function communityCopy(item, language) {
    const messages = {
      follow: "{player} started following you.",
      reaction: "{player} reacted to your post.",
      comment: "{player} commented on your post.",
    };
    const key = messages[item.kind] || "{player} interacted with you.";
    return translate(key, language, { player: item.display_name || item.handle || item.actor_id || "" });
  }

  const legacyTitles = {
    "Hisob email manzili yangilandi": "Email updated",
    "Payout so‘rovi yangilandi": "Payout request updated",
    "Sandbox qaytarimi qayd etildi": "Test refund recorded",
    "TEST · Spin & Win winner": "Test Spin & Win winner",
  };
  const legacyBodies = {
    "Moderator sandbox qaytarimini qayd etdi; haqiqiy pul o‘tkazilmagan.": "A moderator recorded the test refund. No real money was transferred.",
    "Moderator sandbox qaytarimini qayd etdi; haqiqiy pul o‘tkazilmadi.": "A moderator recorded the test refund. No real money was transferred.",
    "Moderator tekshiruvni tasdiqladi. Mablag‘ sandbox sotuvchi balansiga yozildi; haqiqiy pul o‘tkazilmadi.": "A moderator approved the review. The seller’s test balance was credited. No real money was transferred.",
    "Moderator dalillarni ko‘rib, buyurtmani yakunladi. Bu sandbox hisob-kitobi.": "A moderator reviewed the evidence and completed the test order.",
    "Buyurtma sandbox sotuvchi balansiga o‘tkazildi. Haqiqiy pul o‘tkazilmagan.": "The order was credited to the seller’s test balance. No real money was transferred.",
    "Sinov buyurtmasi bekor qilindi. Bu haqiqiy pul qaytarimi emas.": "The test order was cancelled. No real money was refunded.",
    "Sinov buyurtmasi qaytarim bilan yopildi; haqiqiy pul ko‘chirilmagan.": "The test order was closed with a refund. No real money was transferred.",
    "So‘rov ma’qullandi; pulni tashqi provayder orqali o‘tkazing.": "The payout was approved. Send the funds through the external provider.",
  };

  // Match historical server copy while keeping names, references and notes as supplied.
  const bodyTemplates = [
    ["order", /^([\w-]+) bo‘yicha to‘lov tasdiqlandi\.$/, "Payment for {reference} was confirmed.", ["reference"]],
    ["order", /^([\w-]+) · Stripe TEST payment received\.$/, "{reference} · Stripe test payment received.", ["reference"]],
    ["seller_review", /^(.+) do‘koni tekshiruvga yuborildi\.$/s, "The shop {shop} was submitted for review.", ["shop"]],
    ["account_review", /^([\w-]+) uchun xaridor dalillari ko‘rib chiqilishi kerak\.$/, "Buyer evidence for {reference} needs review.", ["reference"]],
    ["account_review", /^([\w-]+) buyurtmasi admin tekshiruvini kutmoqda\.$/, "Order {reference} is awaiting administrator review.", ["reference"]],
    ["dispute", /^([\w-]+): moderator ko‘rib chiqadi\.$/, "A moderator will review {reference}.", ["reference"]],
    ["dispute", /^([\w-]+) buyurtmasi ko‘rib chiqilishi kerak\.$/, "Order {reference} needs review.", ["reference"]],
    ["favorite", /^(.+): narx o‘zgardi: (\d+) → (\d+) ([A-Z]{3})\.$/s, "Price for {listing} changed from {old} to {price} {currency}.", ["listing", "old", "price", "currency"]],
    ["favorite", /^(.+): yana mavjud\.$/s, "{listing} is available again.", ["listing"]],
    ["payout", /^Tashqi o‘tkazma tasdiqlandi\. ID: (.+)$/s, "External transfer confirmed. ID: {reference}", ["reference"]],
  ];
  const listingStates = {
    published: "Your listing has been published.",
    approved_private: "Your listing was approved for private access.",
    rejected: "Your listing was rejected.",
    paused: "Your listing was paused.",
  };
  const reviewFlags = new Map([
    ["off_platform_contact_or_payment", "Possible contact or payment outside the platform"],
    ["possible_credential_or_code", "Possible password or access code"],
    ["possible_duplicate_listing", "Possible duplicate listing"],
    ["high_account_listing_volume", "High number of account listings"],
  ]);
  const prizeStates = {
    new: "New prize",
    contacted: "Winner contacted",
    shipped: "Prize shipped",
    delivered: "Prize delivered",
  };
  const systemBodyKinds = new Set([
    "order_complete", "review", "request", "security", "identity_review",
    "account_review", "dispute_update", "order", "delivery", "moderation", "payout",
  ]);
  let sourceDictionary;
  let notificationKeys;

  function marketplaceCopy(item, language) {
    const dictionary = window.SENTRYLOOT_LANGUAGE_DATA?.notificationMessages?.uz;
    if (!dictionary) return { title: item.title, body: item.body };
    if (dictionary !== sourceDictionary) {
      sourceDictionary = dictionary;
      notificationKeys = new Map(Object.entries(dictionary).map(([key, value]) => [value, key]));
    }
    const t = (key, values) => translate(key, language, values);
    const title = legacyTitles[item.title] || notificationKeys.get(item.title) || item.title;
    const body = String(item.body ?? "");

    function bodyCopy() {
      if (item.kind === "message") {
        if (title === "New image" && body === "Suhbatda yangi rasm bor.")
          return t("There is a new image in your conversation.");
        return body === "Suhbatda yangi xabar bor." && /^\/?#?conversation\//.test(item.href)
          ? t("There is a new message in your conversation.") : body;
      }
      if (item.kind === "moderation" && title === "Listing review result") {
        const match = /^E’loningiz holati: (\w+)\.\s*(.*)$/s.exec(body);
        if (match && Object.hasOwn(listingStates, match[1])) {
          const automatic = /^E’lon moderator tomonidan ko‘rib chiqilib tasdiqlandi\.(?: Tekshiruv signallari: (.+))?$/s.exec(match[2]);
          const flags = automatic?.[1]?.split(", ").map((flag) => t(reviewFlags.get(flag.replace(/\.$/, "")) || flag)).join(", ");
          const note = automatic
            ? [t("The listing was reviewed and approved by a moderator."), flags && t("Review flags: {flags}", { flags })].filter(Boolean).join(" ")
            : match[2];
          return [t(listingStates[match[1]]), note].filter(Boolean).join(" ");
        }
      }
      if (item.kind === "spin_win" || item.kind === "spin_win_admin") {
        const status = /^(.+) · (new|contacted|shipped|delivered)$/.exec(body);
        if (status && title === "Prize update") return status[1] + " · " + t(prizeStates[status[2]]);
        const award = /^(.+) · award: (.+)$/.exec(body);
        if (award) return award[1] + " · " + t("Award {reference}", { reference: award[2] });
        return body;
      }
      if (item.kind === "account" || item.kind === "payout") {
        const prefixes = {
          "Hisobingiz vaqtincha cheklangan. Sabab: ": "Your account was temporarily restricted.",
          "Hisobingiz qayta yoqildi. ": "Your account was reactivated.",
          "Payout so‘rovi rad etildi. ": "The payout request was rejected.",
        };
        for (const [source, key] of Object.entries(prefixes)) {
          if (body.startsWith(source)) return [t(key), body.slice(source.length)].filter(Boolean).join(" ");
        }
      }
      for (const [kind, pattern, key, names] of bodyTemplates) {
        if (kind !== item.kind) continue;
        const match = pattern.exec(body);
        if (match) return t(key, Object.fromEntries(names.map((name, index) => [name, match[index + 1]])));
      }
      if (systemBodyKinds.has(item.kind)) {
        const key = legacyBodies[body] || notificationKeys.get(body);
        if (key) return t(key);
      }
      return body;
    }

    const translatedTitle = Object.hasOwn(dictionary, title) || title === "Spin & Win" ? t(title) : item.title || t("Account notification");
    return { title: translatedTitle, body: bodyCopy() };
  }

  function timestamp(datetime, language) {
    const source = String(datetime ?? "").trim().replace(" ", "T").replace(/([+-]\d{2})$/, "$1:00");
    const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(source) ? source : source + "Z");
    if (!Number.isFinite(date.getTime())) return {};
    const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
    const relative = (key, count) => translate(key, language, { count: count.toLocaleString(language) });
    const fullTime = date.toLocaleString(language, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    let time = date.toLocaleDateString(language);
    if (minutes < 1) time = translate("Just now", language);
    else if (minutes < 60) time = relative("{count} min ago", minutes);
    else if (minutes < 1440) time = relative("{count} hr ago", Math.floor(minutes / 60));
    else if (minutes < 10080) time = relative("{count} d ago", Math.floor(minutes / 1440));
    return { time, datetime: date.toISOString(), fullTime };
  }

  window.NotificationPanel = { bind, close, open, copy, translate, communityCopy, marketplaceCopy, timestamp };
})();
