/* SentryLoot community: same-origin API, persisted state, escaped user content. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s),
    $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icon = (n) =>
    `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  let state = { user: null, profile: null, games: [], csrf: "", admin: false },
    lang = "en",
    routeId = 0,
    activePosts = [],
    composer = null,
    dirty = false,
    pendingLink = "",
    uploading = 0;
  let filters = { kind: "", game: "", mode: "", folder: "" },
    controlSeq = 0,
    gamesScroll = 0;
  const shell = $("#shell"),
    dialog = $("#dialog");
  lang = window.CommunityI18n.language();
  const t = (s) => window.CommunityI18n.translate(s, lang);
  function syncLanguage() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    const skip = $(".skip");
    if (skip) skip.textContent = t("Skip to content");
    const boot = $(".boot>span");
    if (boot) boot.textContent = t("Loading your gaming world…");
  }
  syncLanguage();
  const safeURL = (v) =>
    typeof v === "string" &&
    (/^\/api\/community\/media\/[A-Za-z0-9_-]+(?:\?review=1)?$/.test(v) ||
      /^https:\/\/[^\s"<>]+$/.test(v))
      ? esc(v)
      : "";
  const avatar = (p, size = "") =>
    window.SentryLootAccount.avatar(
      p?.display_name || p?.handle,
      p?.avatar_url,
      "avatar " + size,
      p?.id,
    );
  const gameName = (slug) =>
    state.games.find((g) => g.slug === slug)?.name || slug;
  const button = (label, action, cls = "") =>
    `<button type="button" class="btn ${cls}" data-action="${esc(action)}">${t(label)}</button>`;
  const link = (href, label, cls = "", ico = "") =>
    `<a class="${cls}" href="${esc(href)}">${ico ? icon(ico) : ""}${t(label)}</a>`;
  const empty = (
    title,
    body,
    action = "create",
    label = "Add to showcase",
    ico = "layers",
  ) =>
    `<section class="empty"><span class="empty-icon">${icon(ico)}</span><h2>${t(title)}</h2><p>${t(body)}</p>${action && label !== "Add to showcase" ? button(label, action, "primary") : ""}</section>`;
  const heading = (title, subtitle, action = "") =>
    `<div class="heading"><div><h1>${t(title)}</h1><p>${t(subtitle)}</p></div>${action}</div>`;
  function date(value) {
    try {
      return new Intl.DateTimeFormat(lang, {
        month: "short",
        day: "numeric",
      }).format(new Date(value.includes("T") ? value : value + "Z"));
    } catch {
      return "";
    }
  }
  async function api(path, options = {}) {
    const headers = { "X-CSRF-Token": state.csrf, ...options.headers };
    let body = options.body;
    if (body && !(body instanceof Blob)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    const response = await fetch("/api/" + path, {
      ...options,
      headers,
      body,
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(t(result.error || "Please try again."));
      error.status = response.status;
      throw error;
    }
    return result;
  }
  async function refresh() {
    state = { ...state, ...(await api("community/meta")) };
    lang = window.CommunityI18n.language(state.user);
    syncLanguage();
    const b = $("#account-button");
    if (b && state.user)
      b.innerHTML = window.SentryLootAccount.avatar(
        state.user.display_name || state.user.email,
        state.user.avatar_url,
        "account-avatar",
        state.user.id,
      );
  }
  function toast(message) {
    $("#toast").textContent = t(message);
    $("#toast").classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => $("#toast").classList.remove("show"), 4200);
  }
  function modal(title, body, wide = false) {
    dialog.innerHTML = `<form method="dialog" class="dialog-head"><h2 id="dialog-title">${t(title)}</h2><button class="icon-btn" aria-label="${t("Close")}">${icon("close")}</button></form><div class="dialog-body">${body}</div>`;
    dialog.classList.toggle("wide", wide);
    dialog.showModal();
  }
  function requireAuth() {
    if (state.user?.email_verified) return true;
    modal(
      "Your gaming world awaits",
      `<p>${t(state.user ? "Verify your email before posting, following or saving." : "Sign in to share your moments and build your showcase.")}</p>${link(state.user ? "/#account" : "/#login", state.user ? "My account" : "Sign in", "btn primary")}`,
    );
    return false;
  }
  function meRoute(section = "u") {
    return state.user ? `#${section}/${state.user.id}` : "#" + section + "/me";
  }
  function nav(active) {
    const list = [
      ["discover", "Discover", "home", "#discover"],
      ["following", "Following", "users", "#following"],
      ["u", "My showcase", "user", meRoute()],
      ["collection", "Collection", "layers", meRoute("collection")],
      ["moments", "Moments", "file-text", meRoute("moments")],
      ["saved", "Saved", "heart", "#saved"],
    ];
    return list
      .map(([id, label, ico, href]) =>
        link(href, label, `nav-link ${active === id ? "active" : ""}`, ico),
      )
      .join("");
  }
  function frame(active) {
    const search =
      new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
    shell.innerHTML = `<header class="community-header"><a class="brand" href="/#home" aria-label="SentryLoot — GameStoreHub marketplace" title="SentryLoot · gamestorehub.com"><span class="brand-mark"><img src="https://images.gamestorehub.com/site-assets/sl-d318d339cc8c7e13/sentryloot-mark-256.webp?v=1" alt=""></span><span class="brand-wordmark">Sentry<span class="brand-dot">Loot</span></span></a><nav class="global-nav" aria-label="${t("Main navigation")}">${link("#discover", "Discover", "selected", "globe")}${link("/#home", "Marketplace", "", "cart")}${link("/top-up", "Top Up", "", "wallet")}</nav><form id="search"><label class="sr-only" for="community-search">${t("Search players, moments, collections…")}</label>${icon("search")}<input id="community-search" type="search" name="q" maxlength="80" value="${esc(search)}" placeholder="${t("Search players, moments, collections…")}"></form><div class="header-actions"><button class="icon-btn" data-action="create" aria-label="${t("Add to showcase")}">${icon("upload")}</button><a href="#notifications" class="icon-btn notification-bell ${active === "notifications" ? "gold" : ""}" aria-label="${t("Notifications")}">${icon("bell")}${state.unread ? '<span class="notification-dot"></span>' : ""}</a>${state.user ? `<button id="account-button" type="button" class="account-button is-profile-trigger" data-action="account-menu" aria-label="${t("Open profile menu")}" aria-haspopup="dialog" aria-controls="profile-dropdown" aria-expanded="false">${window.SentryLootAccount.avatar(state.user.display_name || state.user.email, state.user.avatar_url, "account-avatar", state.user.id)}</button>` : link("/#login", "Sign in", "btn small")}</div>${active === "discover" ? gamePills() : ""}</header>
 <aside class="sidebar"><nav aria-label="${t("Community navigation")}">${nav(active)}<div class="nav-rule"></div>${link("#settings", "Settings", `nav-link ${active === "settings" ? "active" : ""}`, "settings")}</nav><div class="my-games"><p>${t("My games")}</p>${(state.profile?.preferences?.games || []).map((g) => `<a href="#discover?game=${esc(g)}">${icon("gamepad")}${esc(gameName(g))}</a>`).join("")}${link("#settings", "Add a game", "", "plus")}</div><div class="sidebar-note"><span>SENTRYLOOT</span><h3>${t("Play. Collect. Connect.")}</h3><p>${t("A place for your gaming story.")}</p>${link("/about", "About us")}${link("/privacy-policy", "Privacy Policy")}${link("/support", "Help")}${link("#safety", "Safety & rights")}${state.user ? link("#submissions", "My submissions & requests") : ""}</div></aside>
 <main id="main" tabindex="-1"><div id="view" class="page ${active === "discover" ? "has-game-pills" : ""}"><div class="skeleton"><i></i><i></i><i></i></div></div></main><nav class="mobile-nav" aria-label="${t("Community navigation")}">${[
   ["discover", "Discover", "home", "#discover"],
   ["following", "Following", "users", "#following"],
   ["create", "Create", "plus", "#create"],
   ["saved", "Saved", "heart", "#saved"],
   ["u", "Showcase", "user", meRoute()],
 ]
   .map(([id, label, ico, href]) =>
     link(href, label, id === active ? "active" : "", ico),
   )
   .join("")}</nav>`;
    $("#search").onsubmit = (e) => {
      e.preventDefault();
      location.hash =
        "search?q=" +
        encodeURIComponent(new FormData(e.target).get("q").trim());
    };
  }

  function accountText(uz, ru, en) {
    return lang === "uz" ? uz : lang === "ru" ? ru : t(en);
  }
  function closeAccountMenu(focus = true) {
    const root = $("#profile-menu-root");
    if (!root) return;
    root.hidden = true;
    root.innerHTML = "";
    document.body.classList.remove("profile-menu-open");
    $("#account-button")?.setAttribute("aria-expanded", "false");
    if (focus) $("#account-button")?.focus({ preventScroll: true });
  }
  async function openAccountMenu() {
    await refresh();
    if (!state.user) {
      await render();
      return;
    }
    const trigger = $("#account-button");
    if (trigger)
      trigger.innerHTML = window.SentryLootAccount.avatar(
        state.user.display_name || state.user.email,
        state.user.avatar_url,
        "account-avatar",
        state.user.id,
      );
    const value = state.user.created_at || "",
      created = new Date(
        value.includes("T") ? value : value.replace(" ", "T") + "Z",
      ).toLocaleDateString(lang, { year: "numeric", month: "long" });
    const root = $("#profile-menu-root");
    root.innerHTML = window.SentryLootAccount.menu(state.user, {
      t: accountText,
      icon,
      created,
    });
    root.hidden = false;
    document.body.classList.add("profile-menu-open");
    trigger?.setAttribute("aria-expanded", "true");
    $("#profile-dropdown")?.focus({ preventScroll: true });
    const balance = $("#profile-bonus-balance");
    try {
      const b = await api("bonuses");
      if (balance.isConnected)
        balance.textContent =
          (Number(b.real_points) || 0).toLocaleString(lang) +
          " " +
          accountText("ball", "баллов", "points") +
          (b.preview_points
            ? " · " +
              Number(b.preview_points).toLocaleString(lang) +
              " " +
              accountText("sinov", "тест", "preview")
            : "");
    } catch {
      if (balance.isConnected)
        balance.textContent = accountText(
          "Yuklanmadi",
          "Не загрузилось",
          "Unavailable",
        );
    }
  }
  async function accountLogout() {
    if ("serviceWorker" in navigator) {
      try {
        const r = await navigator.serviceWorker.getRegistration("/");
        if (r?.active?.scriptURL.endsWith("/push-worker.js")) {
          const sub = await r.pushManager.getSubscription();
          if (sub) {
            try {
              await api("push/subscriptions", {
                method: "DELETE",
                body: { endpoint: sub.endpoint },
              });
            } finally {
              await sub.unsubscribe();
            }
          }
        }
      } catch {}
    }
    await api("logout", { method: "POST", body: {} });
    closeAccountMenu(false);
    location.assign("/#home");
  }

  function tabs(items, selected, attr = "kind") {
    return `<div class="tabs" role="group">${items.map(([value, label]) => `<button type="button" class="tab ${selected === value ? "selected" : ""}" data-filter="${attr}" data-value="${esc(value)}" aria-pressed="${selected === value}">${t(label)}</button>`).join("")}</div>`;
  }

  function gamePills() {
    return state.games.length
      ? `<nav class="game-pills-nav" aria-label="${t("Games")}"><div class="game-pills-scroll"><button type="button" class="game-pill" data-action="game-pill" data-game="" aria-pressed="${!filters.game}">${t("All")}</button>${state.games.map((game) => `<button type="button" class="game-pill" data-action="game-pill" data-game="${esc(game.slug)}" aria-pressed="${filters.game === game.slug}" title="${filters.game === game.slug ? t("All games") : esc(game.name)}">${esc(game.name)}</button>`).join("")}</div><div class="game-pills-edge game-pills-start" hidden><button type="button" class="game-pills-arrow" data-action="scroll-games" data-direction="-1" aria-label="${t("Previous games")}">${icon("chevron")}</button></div><div class="game-pills-edge game-pills-end" hidden><button type="button" class="game-pills-arrow" data-action="scroll-games" data-direction="1" aria-label="${t("Next games")}">${icon("chevron")}</button></div></nav>`
      : "";
  }
  function bindGamePills() {
    const nav = $(".game-pills-nav"),
      row = $(".game-pills-scroll");
    if (!nav || !row) return;
    const sync = () => {
      nav.querySelector(".game-pills-start").hidden = row.scrollLeft <= 2;
      nav.querySelector(".game-pills-end").hidden =
        row.scrollWidth - row.clientWidth - row.scrollLeft <= 2;
    };
    row.scrollLeft = gamesScroll;
    row.querySelector('[aria-pressed="true"]')?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: "instant",
    });
    row.addEventListener(
      "scroll",
      () => {
        gamesScroll = row.scrollLeft;
        sync();
      },
      { passive: true },
    );
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(row);
    const cleanup = new MutationObserver(() => {
      if (!row.isConnected) {
        observer.disconnect();
        cleanup.disconnect();
      }
    });
    cleanup.observe(shell, { childList: true, subtree: true });
  }
  function card(p, mode = "") {
    const image = p.thumbnail_url || p.media_url,
      video = p.media_type?.startsWith("video/"),
      type =
        p.kind === "achievement"
          ? "star"
          : p.kind === "item"
            ? "gem"
            : "file-text";
    return `<article class="post-card ${esc(p.kind)} ${mode}" data-post="${esc(p.id)}"><a class="card-art ${!image ? "no-art" : ""}" href="#moment/${esc(p.id)}" aria-label="${esc(p.title)}">${image && (!video || p.thumbnail_url) ? `<img src="${safeURL(image)}" alt="" loading="lazy" decoding="async">` : p.media_type === "video/stream" ? icon("gamepad") : video ? `<video src="${safeURL(p.media_url)}#t=0.1" preload="metadata" muted playsinline></video>` : icon(type)}<span class="type-tag">${icon(type)}${t(p.promotion ? "For sale" : p.kind === "item" ? "Collection" : p.kind === "achievement" ? "Achievement" : "Moment")}</span>${p.media?.length > 1 ? `<span class="album-count">${icon("layers")}${p.media.length}</span>` : ""}${video ? `<span class="play">${icon("arrow-right")}</span>` : ""}<div class="art-title"><span>${esc(gameName(p.game_slug))}</span><h2>${esc(p.title)}</h2></div></a><div class="card-body">${listingPanel(p)}<p class="card-story" data-user-content>${esc(p.body)}</p><div class="byline"><a href="#u/${esc(p.author.id)}">${avatar(p.author)}<span><strong>${esc(p.author.display_name)}</strong><small>@${esc(p.author.handle)} · ${date(p.created_at)}</small></span></a><button class="icon-btn" data-action="post-menu" data-id="${esc(p.id)}" aria-label="${t("Post options")}">···</button></div><div class="card-actions"><button data-action="like" data-id="${esc(p.id)}" aria-label="${t("Like")}" aria-pressed="${!!p.liked}">${icon("heart")}<span>${p.reactions}</span></button><a href="#moment/${esc(p.id)}" aria-label="${t("Comments")}">${icon("message")}${p.comments}</a><button data-action="save" data-id="${esc(p.id)}" aria-pressed="${!!p.saved}" aria-label="${t("Save")}">${icon("layers")}</button><button data-action="share" data-id="${esc(p.id)}" aria-label="${t("Share")}">${icon("share")}</button>${p.status === "draft" ? `<span class="tag">${t(p.review_status === "pending" ? "Awaiting review" : "Draft")}</span>` : ""}</div></div></article>`;
  }
  function playerCard(p) {
    return `<article class="player-card"><a class="player-main" href="#u/${esc(p.id)}">${avatar(p, "large")}<strong>${esc(p.display_name)}</strong><small>@${esc(p.handle)}</small></a><p data-user-content>${esc(p.bio || t("A new story on SentryLoot."))}</p><div class="row"><small>${p.followers} ${t("followers")}</small>${p.id !== state.user?.id ? `<button class="btn small ${p.following ? "" : "outline"}" data-action="follow" data-id="${esc(p.id)}" data-enabled="${!p.following}">${t(p.following ? "Following" : "Follow")}</button>` : ""}</div></article>`;
  }
  const queryString = (o) =>
    new URLSearchParams(
      Object.entries(o).filter(
        ([, v]) => v !== "" && v !== undefined && v !== null,
      ),
    ).toString();
  function storyPrompt() {
    return `<section class="prompt-panel"><span class="eyebrow">${t("YOUR STORY BELONGS HERE")}</span><h2>${t("Your next great play belongs here.")}</h2><p>${t("Share gameplay, show what you sell, or join the conversation with a comment.")}</p>${button("Share your story", "create", "primary")}</section>`;
  }
  async function feed(page, params) {
    const modes = { following: "following", saved: "saved", drafts: "drafts" };
    let mode = modes[page] || "";
    if (mode && !requireAuth())
      return empty(
        "Your gaming world awaits",
        "Sign in to share your moments and build your showcase.",
        "",
        "",
      );
    const query = params.get("q") || "";
    filters.game = params.get("game") || filters.game;
    const result = await api(
      "community/posts?" +
        queryString({
          mode,
          kind: filters.kind,
          game: filters.game,
          q: query,
          folder: filters.folder,
        }),
    );
    activePosts = result.posts;
    const titles = {
      discover: [
        "Your gaming world, today.",
        "New moments, fresh collections, familiar players.",
      ],
      following: [
        "From your circle.",
        "The latest stories from the players you follow.",
      ],
      saved: [
        "Your saved collection.",
        "Moments and collections worth coming back to. Only you can see this.",
      ],
      search: [
        "Find your next connection.",
        "Players, gameplay moments and collections — all in one place.",
      ],
      drafts: [
        "Stories in the making.",
        "Pick up where you left off. Your drafts are only visible to you.",
      ],
    };
    const [title, sub] = titles[page] || titles.discover;
    let people = "";
    if (page === "search") {
      const p = await api("community/players?q=" + encodeURIComponent(query));
      people = p.players.length
        ? `<section><div class="section-title"><h2>${t("Players")}</h2></div><div class="players-grid">${p.players.map(playerCard).join("")}</div></section>`
        : "";
    }
    let folders = "";
    if (page === "saved" && state.user) {
      const f = await api("community/folders");
      folders = `<div class="folders">${button("New folder", "new-folder", "outline")}${f.folders.map((f) => `<button class="chip ${filters.folder === f ? "selected" : ""}" data-filter="folder" data-value="${esc(f)}">${icon("layers")}${esc(f)}</button>`).join("")}</div>`;
    }
    return `${page === "discover" ? "" : heading(title, sub, page === "drafts" ? "" : "")}<div class="feed-layout"><div class="feed-main"><div class="toolbar ${page === "discover" ? "discover-toolbar" : ""}">${tabs(
      [
        ["", "All"],
        ["moment", "Moments"],
        ["item", "Collections"],
        ["achievement", "Achievements"],
      ],
      filters.kind,
    )}</div>${folders}${people}<div class="post-grid discover-grid" id="posts">${result.posts.map((p, i) => card(p)).join("")}</div>${!result.posts.length ? empty(page === "saved" ? "Nothing saved just yet." : page === "following" ? "Your circle starts here." : page === "search" ? "No stories found." : "Every great story starts somewhere.", page === "following" ? "Follow a player to see their new posts here." : "Share a moment, a favorite item or a milestone. This space grows with you.", page === "following" ? "find-players" : "create", page === "following" ? "Find players" : "Add to showcase") : ""}${result.next !== null ? `<button class="btn load-more" data-action="more" data-offset="${result.next}" data-mode="${mode}" data-query="${esc(query)}">${t("Load more")}</button>` : ""}</div></div>`;
  }
  async function profilePage(page, id, params) {
    if (!id || id === "me") {
      if (!requireAuth())
        return empty(
          "Your showcase, your story.",
          "Sign in to create a home for your gaming journey.",
          "",
          "",
        );
      id = state.user.id;
    }
    let p;
    try {
      p = await api("community/profiles/" + encodeURIComponent(id));
    } catch (e) {
      if (e.status === 404 && id === state.user?.id)
        return empty(
          "Make this space yours.",
          "Set up your profile, choose your games and start your showcase.",
          "edit",
          "Create my showcase",
        );
      throw e;
    }
    const result = await api(
      "community/posts?" +
        queryString({
          user: p.id,
          kind:
            page === "collection"
              ? "item"
              : page === "moments"
                ? "moment"
                : filters.kind,
          game: filters.game,
        }),
    );
    activePosts = result.posts;
    const owner = p.owner && params.get("visitor") !== "1";
    const name = esc(p.display_name);
    const hero = `<section class="profile-hero"><div class="profile-cover ${p.cover_url ? "" : "abstract-cover"}">${p.cover_url ? `<img src="${safeURL(p.cover_url)}" alt="" fetchpriority="high">` : ""}${owner ? button("Edit cover", "edit", "glass cover-edit") : ""}</div><div class="profile-info">${avatar(p, "hero-avatar")}<div class="profile-identity"><span class="eyebrow">${t("PLAYER SHOWCASE")}</span><h1 data-user-content>${name}</h1><div class="muted">@${esc(p.handle)}${p.country ? " · " + esc(p.country) : ""}</div><p data-user-content>${esc(p.bio || t("A new story on SentryLoot."))}</p></div><div class="profile-stats">${link("#circle/" + p.id + "?mode=followers", `${p.followers} ${t("followers")}`)}${link("#circle/" + p.id + "?mode=following", `${p.following_count} ${t("following")}`)}</div><div class="profile-cta">${owner ? "" + button("Edit profile", "edit", "outline") : `<button class="btn primary" data-action="follow" data-id="${p.id}" data-enabled="${!p.following}">${t(p.following ? "Following" : "Follow")}</button><button class="btn outline" data-action="share-profile" data-id="${p.id}">${t("Share showcase")}</button>`}</div></div></section>`;
    const selected =
      page === "u"
        ? "Showcase"
        : page === "collection"
          ? "Collection"
          : page === "about"
            ? "About"
            : "Moments";
    const subnav = `<nav class="profile-tabs">${[
      ["u", "Showcase", "layers"],
      ["moments", "Moments", "file-text"],
      ["collection", "Collection", "gem"],
      ["about", "About", "info"],
    ]
      .map(([route, title, ico]) =>
        link(
          "#" + route + "/" + p.id,
          title,
          selected === title ? "selected" : "",
          ico,
        ),
      )
      .join("")}</nav>`;
    let posts = result.posts;
    if (owner && page === "u")
      posts = [...posts].sort((a, b) => {
        const ai = p.layout.indexOf(a.id),
          bi = p.layout.indexOf(b.id);
        return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi) || b.pinned - a.pinned;
      });
    if (!owner && p.owner) posts = posts.filter((p) => p.audience === "public");
    const head =
      page === "collection"
        ? [
            "Your collection, your way.",
            "Every item has a story. Keep yours here.",
          ]
        : page === "moments"
          ? [
              "Moments worth keeping.",
              "The clutches, comebacks and little victories.",
            ]
          : [
              "Pinned to the showcase",
              "Highlights, favorite collectibles and key achievements.",
            ];
    let main =
      page === "about"
        ? `<section class="panel prose"><h2>${t("About this player")}</h2><p data-user-content>${esc(p.bio || t("This player has not added a bio yet."))}</p><p>${t("Joined")} ${date(p.created_at)}</p><p>${t("Collections are shared by players. They are not verified game inventories or items for sale.")}</p></section>`
        : `<div class="section-title"><div><h2>${t(head[0])}</h2><p>${t(head[1])}</p></div>${owner ? link("#layout", "Manage pins", "btn outline", "layers") : ""}</div><div class="toolbar">${owner && page === "moments" ? link("#drafts", "Drafts", "btn outline") : ""}</div><div id="posts" class="post-grid discover-grid">${posts.map((p) => card(p)).join("")}</div>${!posts.length ? empty(owner ? "Your showcase is waiting." : "A story is on its way.", owner ? "Add your first moment, collection item or achievement." : "This player has not shared anything here yet.", owner ? "create" : "", owner ? "Add to showcase" : "") : ""}${result.next !== null ? `<button class="btn load-more" data-action="more" data-offset="${result.next}" data-user="${p.id}" data-kind="${page === "collection" ? "item" : page === "moments" ? "moment" : ""}">${t("Load more")}</button>` : ""}`;
    return `<div class="profile-layout"><div>${hero}${subnav}${owner ? `<nav class="profile-tools">${link("#drafts", "Drafts", "chip", "file-text")}${link("#layout", "Manage showcase", "chip", "layers")}${link("#settings", "Settings", "chip", "settings")}${link("#u/" + p.id + "?visitor=1", "View as visitor", "chip", "eye")}</nav>` : ""}${main}</div></div>`;
  }
  function collectionInspector(p) {
    return `<section class="panel collection-inspector">${p.media_url ? (p.media_type === "video/mp4" ? `<video class="item-portrait" controls playsinline preload="metadata" src="${safeURL(p.media_url)}"></video>` : `<img class="item-portrait" src="${safeURL(p.thumbnail_url || p.media_url)}" alt="${esc(p.title)}">`) : ""}<h2 data-user-content>${esc(p.title)}</h2><span class="tag">${esc(gameName(p.game_slug))}</span><div class="inspector-story"><span class="eyebrow">${t("THE STORY BEHIND IT")}</span><p data-user-content>${esc(p.body)}</p></div>${link("#moment/" + p.id, "View item story", "btn outline full", "arrow-right")}<button class="btn full" data-action="save" data-id="${p.id}" aria-pressed="${!!p.saved}">${icon("layers")}${t(p.saved ? "Saved" : "Save")}</button><small>${t("Collections are shared by players. They are not verified game inventories or items for sale.")}</small></section>`;
  }
  async function collectionPage(id) {
    if (!id || id === "me") {
      if (!requireAuth())
        return empty(
          "Your collection, your way.",
          "Sign in to create your showcase.",
          "",
          "",
        );
      id = state.user.id;
    }
    let p;
    try {
      p = await api("community/profiles/" + encodeURIComponent(id));
    } catch (e) {
      if (e.status === 404 && id === state.user?.id)
        return empty(
          "Make this space yours.",
          "Set up your profile, choose your games and start your showcase.",
          "edit",
          "Create my showcase",
        );
      throw e;
    }
    const result = await api(
      "community/posts?" +
        queryString({ user: p.id, kind: "item", game: filters.game }),
    );
    activePosts = result.posts;
    const selected = result.posts[0];
    const shelf = result.posts.slice(0, 3);
    return `${link("#u/" + p.id, "Back to showcase", "back", "arrow-right")}${heading("Your collection, your way.", "Every item has a story. Keep yours here.", p.owner ? button("Add an item", "collection-create", "primary") : `<button class="btn outline" data-action="share-profile" data-id="${p.id}">${t("Share showcase")}</button>`)}<div class="collection-layout"><div><div class="toolbar"><a class="byline" href="#u/${p.id}">${avatar(p)}<span><strong>${esc(p.display_name)}</strong><small>@${esc(p.handle)}</small></span></a></div>${shelf.length ? `<section class="collection-shelf"><div><span class="eyebrow">${t("THE FAVOURITES SHELF")}</span><h2>${t("The pieces I kept.")}</h2></div><div class="shelf-items">${shelf.map((item) => `<button class="shelf-piece" data-action="select-item" data-id="${item.id}" aria-label="${esc(item.title)}">${item.media_type?.startsWith("image/") ? `<img src="${safeURL(item.media_url)}" alt="${esc(item.title)}">` : icon("gem")}<strong>${esc(item.title)}</strong></button>`).join("")}</div></section><div class="collection-tiles">${result.posts.map((item) => `<button class="collection-tile ${item.id === selected.id ? "selected" : ""}" data-action="select-item" data-id="${item.id}">${item.media_type?.startsWith("image/") ? `<img src="${safeURL(item.thumbnail_url || item.media_url)}" alt="">` : icon("gem")}<span><small>${esc(gameName(item.game_slug))}</small><strong>${esc(item.title)}</strong></span></button>`).join("")}</div>` : empty("Your showcase is waiting.", "Add your first moment, collection item or achievement.", p.owner ? "collection-create" : "", p.owner ? "Add an item" : "")}${result.next !== null ? `<button class="btn load-more" data-action="more-items" data-user="${p.id}" data-offset="${result.next}">${t("Load more")}</button>` : ""}<section class="panel collection-journal"><span>${icon("clock")}${t("Collection journal")}</span><p>${t("Every item has a story. Keep yours here.")}</p></section></div><aside id="item-inspector">${selected ? collectionInspector(selected) : `<section class="panel"><h2>${t("The pieces I kept.")}</h2><p class="muted">${t("Add a collection item to tag it here.")}</p></section>`}</aside></div>`;
  }
  function relatedPost(p) {
    const video = p.media_type?.startsWith("video/"),
      image = p.thumbnail_url || (!video ? p.media_url : "");
    return `<li><a class="related-post" href="#moment/${esc(p.id)}"><span class="related-art">${image ? `<img src="${safeURL(image)}" alt="" loading="lazy" decoding="async">` : p.media_type === "video/mp4" ? `<video src="${safeURL(p.media_url)}#t=0.1" preload="metadata" muted playsinline aria-hidden="true"></video>` : icon("gamepad")}<span class="related-type">${icon(video ? "arrow-right" : "file-text")}${t(video ? "Video" : "Image")}</span></span><span class="related-copy"><strong data-user-content>${esc(p.title)}</strong><span data-user-content>${esc(p.author.display_name)}</span><small>${esc(gameName(p.game_slug))} · ${date(p.created_at)}</small></span></a></li>`;
  }
  async function momentPage(id) {
    const [p, result] = await Promise.all([
      api("community/posts/" + encodeURIComponent(id)),
      api("community/posts/" + encodeURIComponent(id) + "/comments"),
    ]);
    activePosts = [p];
    const suggestions = await api(
      "community/posts/" + encodeURIComponent(id) + "/related",
    ).catch(() => null);
    const video = p.media_type?.startsWith("video/");
    const media =
      p.media?.length > 1
        ? albumViewer(p)
        : p.media_type === "video/stream"
          ? `<div class="stream-player" data-stream="${safeURL(p.media_url)}"></div>`
          : p.media_url
            ? video
              ? `<video controls playsinline preload="metadata" src="${safeURL(p.media_url)}" ${p.thumbnail_url ? `poster="${safeURL(p.thumbnail_url)}"` : ""}></video>`
              : `<img src="${safeURL(p.media_url)}" alt="${esc(p.title)}">`
            : `<div class="achievement-art">${icon("star")}</div>`;
    const comments = result.comments
      .map(
        (c) =>
          `<article class="comment"><a href="#u/${esc(c.user_id)}">${avatar(c)}</a><div><div class="row"><a href="#u/${esc(c.user_id)}"><strong>${esc(c.display_name)}</strong></a><small>${date(c.created_at)}</small>${state.user && c.user_id !== state.user.id ? link("#request?kind=comment&post=" + p.id + "&comment=" + c.id, "Report comment", "text-link") : ""}${[c.user_id, p.user_id].includes(state.user?.id) ? `<button class="text-link" data-action="delete-comment" data-id="${c.id}">${t("Delete")}</button>` : ""}</div><p data-user-content>${esc(c.body)}</p></div></article>`,
      )
      .join("");
    return `<div class="watch-layout"><div class="detail-layout"><article><div class="media-stage">${media}</div><div class="detail-title"><h1 data-user-content>${esc(p.title)}</h1><p class="muted">${esc(gameName(p.game_slug))} · ${date(p.created_at)} · ${t(p.audience === "public" ? "Public" : p.audience === "followers" ? "Followers only" : "Private")}</p></div><div class="detail-author"><a class="byline" href="#u/${p.author.id}">${avatar(p.author, "large")}<span><strong>${esc(p.author.display_name)}</strong><small>@${esc(p.author.handle)}</small></span></a>${p.owner ? link("#create/" + p.id, "Edit", "btn outline") : `<button class="btn outline" data-action="follow" data-id="${p.author.id}" data-enabled="${!p.author.following}">${t(p.author.following ? "Following" : "Follow")}</button>`}<div class="card-actions"><button data-action="like" data-id="${p.id}" aria-pressed="${!!p.liked}">${icon("heart")}${p.reactions}</button><button data-action="save" data-id="${p.id}" aria-pressed="${!!p.saved}">${icon("layers")}${t("Save")}</button><button data-action="share" data-id="${p.id}">${icon("share")}${t("Share")}</button><button data-action="post-menu" data-id="${p.id}" aria-label="${t("Post options")}">···</button></div></div><div class="panel prose detail-description">${listingPanel(p)}${p.body.length > 220 ? `<details><summary>${t("About this post")}<span>${t("Show more")}</span></summary><p data-user-content>${esc(p.body)}</p></details>` : `<p data-user-content>${esc(p.body)}</p>`}${p.linked_items.length ? `<div class="chips">${p.linked_items.map((id) => link("#moment/" + id, "View collection item", "chip", "gem")).join("")}</div>` : ""}</div><section class="panel detail-comments"><div class="section-title"><h2>${p.comments} ${t("Comments")}</h2></div>${p.comments_enabled ? `<form id="comment-form" data-post="${p.id}"><label class="sr-only" for="comment-body">${t("Add a comment")}</label><textarea id="comment-body" name="body" maxlength="1000" required placeholder="${t("Add a thoughtful comment…")}"></textarea><button class="btn primary" type="submit">${t("Post comment")}</button><p class="form-error" role="alert"></p></form>` : `<p>${t("Comments are closed for this post.")}</p>`}${comments || `<p class="muted">${t("Start the conversation.")}</p>`}</section></article></div><aside class="related-posts" aria-labelledby="related-posts-title"><h2 id="related-posts-title">${t("More from other players")}</h2>${suggestions?.posts.length ? `<ol class="related-list">${suggestions.posts.map(relatedPost).join("")}</ol>` : `<p class="related-empty">${t(suggestions ? "More videos and images will appear here." : "Suggestions are unavailable. Please try again.")}</p>`}</aside></div>`;
  }
  const field = (label, name, value = "", type = "text", max = 80) =>
    `<label class="field"><span>${t(label)}</span>${type === "textarea" ? `<textarea name="${name}" maxlength="${max}" ${name === "body" ? "" : 'rows="4"'}>${esc(value)}</textarea>` : `<input type="${type}" name="${name}" value="${esc(value)}" maxlength="${max}" ${["title", "display_name", "handle"].includes(name) ? "required" : ""}>`}</label>`;
  const select = (label, name, items, value) => {
    const id = "community-field-" + name + "-" + ++controlSeq;
    return `<div class="field"><label for="${id}">${t(label)}</label><select id="${id}" name="${name}">${items.map(([v, l]) => `<option value="${esc(v)}" ${value === v ? "selected" : ""}>${t(l)}</option>`).join("")}</select></div>`;
  };
  function composerMedia() {
    return composer?.media || [];
  }
  function syncComposerMedia() {
    const media = composerMedia();
    composer.media_ids = media.map((m) => m.id);
    composer.media_id = media[0]?.id || null;
    composer.media_url = media[0]?.url || "";
    composer.media_type = media[0]?.content_type || "";
  }
  function mediaPreviews() {
    return composerMedia()
      .map(
        (m) =>
          `<div class="upload-preview-item">${m.content_type === "video/stream" ? `<span>${t("Video uploaded. Check processing before submitting.")}</span>` : m.content_type.startsWith("video/") ? `<video src="${safeURL(m.url)}" controls playsinline preload="metadata"></video>` : `<img src="${safeURL(m.url)}" alt="" decoding="async">`}<button type="button" class="remove-upload" data-action="remove-upload" data-id="${esc(m.id)}" aria-label="${t("Remove media")}">×</button></div>`,
      )
      .join("");
  }
  function renderMediaPreviews() {
    const zone = $(".post-upload");
    if (!zone) return;
    $(".upload-previews", zone).innerHTML = mediaPreviews();
    zone.classList.toggle("has-media", composerMedia().length > 0);
    updateLivePreview();
  }
  function uploadControl(label, name, accept, url = "", video = false) {
    if (name === "post-media")
      return `<div class="field media-upload-field"><div class="upload-zone post-upload ${url ? "has-media" : ""}"><div class="upload-previews">${mediaPreviews()}</div><label class="upload-icon" for="${name}" title="${t("Add images or one video")}">${icon("upload")}<span class="sr-only">${t("Add images or one video")}</span><input id="${name}" type="file" accept="${accept}" multiple data-upload="${name}"></label></div><div class="upload-status" role="status" aria-live="polite"></div></div>`;
    return `<div class="field"><label for="${name}">${t(label)}</label><label class="upload-zone ${url ? "has-media" : ""}" for="${name}">${url ? `<img src="${safeURL(url)}" alt="">` : `<span class="upload-icon">${icon("upload")}</span>`}<strong>${t(url ? "Replace media" : "Choose a file")}</strong><span>${t("Images: JPG, PNG or WebP · up to 4 MB")}</span><input id="${name}" type="file" accept="${accept}" data-upload="${name}"></label><div class="upload-status" role="status"></div></div>`;
  }

  async function createPage(id) {
    if (!requireAuth())
      return empty(
        "Your story belongs here.",
        "Sign in to share your gaming journey.",
        "",
        "",
      );
    let p = id ? await api("community/posts/" + encodeURIComponent(id)) : null;
    if (p && !p.owner) throw Error(t("Only the author can edit this post."));
    composer = p || {
      kind:
        new URLSearchParams(location.hash.split("?")[1] || "").get("kind") ===
        "item"
          ? "item"
          : "moment",
      title: "",
      body: "",
      game_slug:
        state.profile?.preferences?.games?.[0] || state.games[0]?.slug || "",
      media_id: null,
      thumbnail_id: null,
      audience: "public",
      comments_enabled: 1,
      pinned: 0,
      linked_items: [],
    };
    composer.media = Array.isArray(composer.media)
      ? composer.media
      : composer.media_id
        ? [
            {
              id: composer.media_id,
              url: composer.media_url,
              content_type: composer.media_type,
            },
          ]
        : [];
    syncComposerMedia();
    const items = await api(
      "community/posts?user=" + state.user.id + "&kind=item",
    ).catch(() => ({ posts: [] }));
    const offers = await api("community/listings");
    return `${heading("Share something worth keeping.", "A gameplay moment, a favorite collectible or a milestone. Make it yours.")}
 <form id="composer"><div class="compose-layout"><div><div class="tabs compose-tabs">${[
   ["moment", "Moment", "file-text"],
   ["item", "Collection item", "layers"],
   ["achievement", "Achievement", "star"],
 ]
   .map(
     ([k, l, i]) =>
       `<button class="tab ${composer.kind === k ? "selected" : ""}" type="button" data-compose-kind="${k}" ${p ? "disabled" : ""}>${icon(i)}${t(l)}</button>`,
   )
   .join(
     "",
   )}</div><section class="panel">${uploadControl("Your media", "post-media", "image/jpeg,image/png,image/webp,video/mp4", composer.media_url, composer.media_type?.startsWith("video/"))}${select("Promote a listing (optional)", "listing_id", [["", "Gameplay only"], ...offers.listings.map((l) => [l.id, l.title])], composer.listing_id || "")}${field("Title", "title", composer.title)}${field("Story", "body", composer.body, "textarea", 2000)}<div class="form-row">${select(
   "Game",
   "game_slug",
   state.games.map((g) => [g.slug, g.name]),
   composer.game_slug,
 )}<div class="field"><span>${t("Tag collection items")}</span><div class="tag-items">${
   items.posts
     .filter((i) => i.id !== id)
     .map(
       (i) =>
         `<label class="check"><input type="checkbox" name="linked_items" value="${i.id}" ${composer.linked_items.includes(i.id) ? "checked" : ""}>${esc(i.title)}</label>`,
     )
     .join("") ||
   `<p class="muted">${t("Add a collection item to tag it here.")}</p>`
 }</div></div></div></section></div><aside><section class="panel preview-panel"><span class="eyebrow">${t("LIVE POST PREVIEW")}</span><div id="live-preview"></div>${select(
   "Audience",
   "audience",
   [
     ["public", "Public"],
     ["followers", "Followers only"],
     ["private", "Only me"],
   ],
   composer.audience,
 )}<label class="switch-row"><span>${icon("message")}${t("Allow comments")}</span><input type="checkbox" role="switch" name="comments_enabled" ${composer.comments_enabled ? "checked" : ""}></label><label class="switch-row"><span>${icon("layers")}${t("Pin to showcase")}</span><input type="checkbox" role="switch" name="pinned" ${composer.pinned ? "checked" : ""}></label><label class="check permission"><input type="checkbox" name="permission"><span><strong>${t("I have permission to share this content.")}</strong><small>${t("Only upload content you own or are authorized to share.")} ${link("#safety", "Safety & rights")}</small></span></label><p class="muted">${t("When you publish, your caption and resized image or video frames are sent to OpenAI for automatic safety checks.")}</p><p data-safety-status role="status"></p><p class="form-error" role="alert"></p><div class="row"><button class="btn outline" type="submit" name="intent" value="draft">${t("Save draft")}</button><button class="btn primary" type="submit" name="intent" value="published">${icon("send")}${t("Publish")}</button></div></section></aside></div></form>`;
  }
  async function editPage() {
    if (!requireAuth())
      return empty(
        "Make this space yours.",
        "Sign in to create your showcase.",
        "",
        "",
      );
    const p = state.profile || {
      handle: "",
      bio: "",
      display_name: state.user.display_name,
    };
    composer = { cover_id: p.cover_id || null, cover_url: p.cover_url || "" };
    return `${heading("Make it unmistakably you.", "Your profile is the home for your gaming story.")}
 <form id="profile-form" class="compose-layout"><section class="panel">${uploadControl("Cover image", "profile-cover", "image/jpeg,image/png,image/webp", p.cover_url)}<div class="avatar-edit">${avatar(state.user, "large")}<div><label class="btn outline" for="profile-avatar">${t("Change profile picture")}</label><input id="profile-avatar" type="file" accept="image/jpeg,image/png,image/webp" data-upload="profile-avatar"><small>${t("Images: JPG, PNG or WebP · up to 4 MB")}</small></div></div><div class="form-row">${field("Display name", "display_name", p.display_name, "text", 60)}${field("Handle", "handle", p.handle, "text", 24)}</div>${field("Bio", "bio", p.bio, "textarea", 500)}<p class="muted">${t("Your display name and avatar are shared with your SentryLoot account.")}</p><p class="form-error" role="alert"></p><button type="submit" class="btn primary">${t("Save changes")}</button></section><aside class="panel preview-panel"><span class="eyebrow">${t("PROFILE PREVIEW")}</span><div id="profile-preview"></div>${link("#layout", "Arrange your showcase", "btn outline full", "layers")}</aside></form>`;
  }
  async function settingsPage() {
    if (!requireAuth())
      return empty(
        "Your space. Your rules.",
        "Sign in to manage your privacy.",
        "",
        "",
      );
    const p = state.profile || { visibility: "public", preferences: {} };
    const prefs = p.preferences || {};
    const blocks = await api("community/blocks");
    return `${heading("Your space. Your rules.", "Choose what you share, who can interact and what reaches you.")}<form id="settings-form" class="settings-layout"><nav class="settings-nav">${link("#edit", "Edit profile", "nav-link", "user")}${link("#settings", "Privacy & preferences", "nav-link active", "shield")}${link("/#account", "Account security", "nav-link", "settings")}${link("#layout", "Showcase layout", "nav-link", "layers")}</nav><div><section class="panel"><h2>${t("Privacy & interactions")}</h2>${select(
      "Showcase visibility",
      "visibility",
      [
        ["public", "Public"],
        ["followers", "Followers only"],
        ["private", "Only me"],
      ],
      p.visibility,
    )}<label class="switch-row"><span>${t("Show country on my public profile")}</span><input name="show_country" type="checkbox" role="switch" ${prefs.show_country ? "checked" : ""}></label>${select(
      "Who can comment",
      "comments",
      [
        ["everyone", "Everyone"],
        ["following", "Players I follow"],
        ["nobody", "Nobody"],
      ],
      prefs.comments || "everyone",
    )}<p class="muted">${t("Saved posts and drafts are always private. Blocked players cannot view your posts or interact with you.")}</p></section><section class="panel"><h2>${t("Notification preferences")}</h2>${[
      ["notify_follow", "New followers"],
      ["notify_reaction", "Reactions to your posts"],
      ["notify_comment", "Comments on your posts"],
    ]
      .map(
        ([k, l]) =>
          `<label class="switch-row"><span>${t(l)}</span><input name="${k}" type="checkbox" role="switch" ${prefs[k] !== false ? "checked" : ""}></label>`,
      )
      .join(
        "",
      )}</section><section class="panel"><h2>${t("Your games")}</h2><div class="game-choices">${state.games.map((g) => `<label class="chip"><input type="checkbox" name="games" value="${g.slug}" ${(prefs.games || []).includes(g.slug) ? "checked" : ""}>${esc(g.name)}</label>`).join("")}</div></section><section class="panel"><h2>${t("Blocked players")}</h2>${blocks.players.map((p) => `<div class="switch-row"><span>${esc(p.display_name)} <small>@${esc(p.handle)}</small></span><button type="button" class="btn small" data-action="unblock" data-id="${p.id}">${t("Unblock")}</button></div>`).join("") || `<p class="muted">${t("No blocked players.")}</p>`}</section><p class="form-error" role="alert"></p><button class="btn primary" type="submit">${t("Save preferences")}</button></div></form>`;
  }
  async function circlePage(id, params) {
    if (!id) {
      if (!requireAuth())
        return empty(
          "Your gaming world awaits",
          "Sign in to share your moments and build your showcase.",
          "",
          "",
        );
      id = state.user.id;
    }
    const mode = params.get("mode") || "following";
    const result = await api(
      "community/players?" + queryString({ user: id, mode }),
    );
    return `${heading("The players around you.", "Your circle is built one connection at a time.")}<nav class="tabs">${[["following", "Following"], ["followers", "Followers"], ...(id === state.user?.id ? [["squad", "My squad"]] : [])].map(([m, l]) => link("#circle/" + id + "?mode=" + m, l, `tab ${mode === m ? "selected" : ""}`)).join("")}</nav><div class="players-grid">${result.players.map((p) => `<div>${playerCard(p)}${id === state.user?.id && p.id !== id ? `<button class="btn full" data-action="squad" data-id="${p.id}" data-enabled="${mode !== "squad"}">${t(mode === "squad" ? "Remove from squad" : "Add to squad")}</button>` : ""}</div>`).join("")}</div>${!result.players.length ? empty("Your circle starts here.", "Discover players who share your interests.", "find-players", "Find players", "users") : ""}`;
  }
  async function notificationsPage() {
    if (!requireAuth())
      return empty(
        "Your gaming world awaits",
        "Sign in to share your moments and build your showcase.",
        "",
        "",
      );
    const result = await api("community/notifications");
    return `${heading("You’re in the loop.", "The latest connections and conversations in your gaming world.", button("Mark all as read", "read-all", "outline"))}<div class="notification-layout"><section class="panel notification-list">${result.notifications.map((n) => `<a class="notification ${n.seen ? "" : "unread"}" href="${n.post_id ? "#moment/" + n.post_id : "#u/" + n.actor_id}">${avatar(n, "large")}<div><strong>${esc(n.display_name)}</strong> ${t({ follow: "started following you.", reaction: "reacted to your post.", comment: "commented on your post." }[n.kind] || "interacted with you.")}<small>${date(n.created_at)}</small></div>${icon("arrow-right")}</a>`).join("") || empty("All caught up.", "New followers, reactions and conversations will appear here.", "", "", "bell")}</section><aside class="panel"><h2>${t("Make notifications yours.")}</h2><p>${t("Choose which updates you want to receive.")}</p>${link("#settings", "Notification preferences", "btn outline full", "settings")}</aside></div>`;
  }
  async function layoutPage() {
    if (!requireAuth())
      return empty(
        "Your gaming world awaits",
        "Sign in to share your moments and build your showcase.",
        "",
        "",
      );
    const result = await api("community/posts?user=" + state.user.id);
    activePosts = result.posts;
    const order = state.profile?.layout || [];
    const chosen = result.posts
      .filter((p) => order.includes(p.id))
      .sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    const unchosen = result.posts.filter((p) => !order.includes(p.id));
    return `${heading("Your showcase, curated.", "Choose up to 12 highlights. Arrange them in the order visitors will see.")}<form id="layout-form"><div class="layout-editor"><section class="panel"><h2>${t("Pinned highlights")}</h2><p class="muted">${t("Use the arrows to reorder. Uncheck a post to hide it from your pinned highlights.")}</p><div id="layout-items">${[...chosen, ...unchosen].map((p) => `<div class="layout-item" data-pin="${p.id}" draggable="true"><input type="checkbox" name="pins" value="${p.id}" ${order.includes(p.id) || p.pinned ? "checked" : ""} aria-label="${esc(t("Pin") + " " + p.title)}">${p.thumbnail_url || p.media_type?.startsWith("image/") ? `<img src="${safeURL(p.thumbnail_url || p.media_url)}" alt="">` : icon("layers")}<span><strong>${esc(p.title)}</strong><small>${esc(gameName(p.game_slug))}</small></span><button type="button" class="icon-btn" data-action="move-up" aria-label="${t("Move up")}">↑</button><button type="button" class="icon-btn" data-action="move-down" aria-label="${t("Move down")}">↓</button></div>`).join("") || empty("Your showcase is waiting.", "Publish a post to pin it here.", "create")}</div></section><aside class="panel"><h2>${t("A story in every highlight.")}</h2><p>${t("Lead with your favorite moment. Add a collection item. Finish with a milestone.")}</p>${link(meRoute(), "Preview showcase", "btn outline full", "eye")}<p class="form-error" role="alert"></p><button type="submit" class="btn primary full">${t("Save layout")}</button></aside></div></form>`;
  }
  async function moderationPage() {
    const r = await api("admin/community/reports");
    const queue = await reviewQueue();
    return `${queue}${heading("Community moderation", "Review player reports and act on content.")}<section class="panel">${r.reports.map((r) => `<article class="report"><span class="tag">${esc(t(r.status))}</span><h2>${esc(r.title)}</h2><p>${esc(t(r.reason))} · ${date(r.created_at)}</p><p data-user-content>${esc(r.body)}</p><div class="row">${link("#moment/" + r.post_id, "View post", "btn outline")}${["hide", "dismiss", "restore"].map((a) => `<button class="btn" data-action="moderate" data-id="${r.id}" data-moderation="${a}">${t(a === "hide" ? "Hide post" : a === "dismiss" ? "Dismiss report" : "Restore post")}</button>`).join("")}</div></article>`).join("") || `<p>${t("No reports to review.")}</p>`}</section>`;
  }
  function listingPanel(p) {
    if (!p.promotion && !p.listing_id) return "";
    const item = p.listing;
    if (!item)
      return `<div class="sale-link muted">${t("This listing is no longer available.")}</div>`;
    let price;
    try {
      price = new Intl.NumberFormat(lang, {
        style: "currency",
        currency: item.currency,
      }).format(item.price_minor / 100);
    } catch {
      price = item.currency + " " + (item.price_minor / 100).toFixed(2);
    }
    return `<a class="sale-link" href="/listing/${esc(item.id)}"><span>${icon("cart")}<strong>${esc(item.title)}</strong><small>${esc([item.platform, item.region].filter(Boolean).join(" · "))}</small></span><span><strong>${esc(price)}</strong><small>${t(item.available ? "View listing" : "Sold out")}</small></span></a>`;
  }
  async function streamPlayers(root = document) {
    for (const el of $$("[data-stream]", root)) {
      if (el.dataset.loading) continue;
      el.dataset.loading = "1";
      try {
        const response = await fetch(el.dataset.stream, {
          credentials: "same-origin",
        });
        const r = await response.json();
        if (!response.ok) throw Error(r.error || "Video unavailable.");
        if (
          !/^https:\/\/iframe\.videodelivery\.net\/[A-Za-z0-9_.-]+$/.test(
            r.iframe,
          )
        )
          throw Error("Invalid video URL");
        if (!el.isConnected) continue;
        const frame = document.createElement("iframe");
        frame.src = r.iframe;
        frame.title = t("Gameplay video");
        frame.allow = "fullscreen; picture-in-picture";
        frame.allowFullscreen = true;
        frame.referrerPolicy = "no-referrer";
        el.replaceChildren(frame);
      } catch (e) {
        el.textContent = t(e.message);
      }
    }
  }
  async function safetyPage() {
    return `${heading("Community safety", "Share your game. Respect the people behind it.")}<div class="trust-grid"><section class="panel prose"><h2>${t("Content moderation")}</h2><p>${t("Posts and edits are checked automatically for violence, nudity, dangerous real-world acts and recreational drug content. Ordinary non-graphic gameplay is allowed. Flagged or inconclusive posts stay private. You can edit the post, report content, block players or appeal a decision.")}</p><h2>${t("What belongs here")}</h2><p>${t("Share gameplay, helpful tips and honest demonstrations of your own listings. No scams, stolen accounts, harassment, hate, sexual exploitation, personal data exposure or illegal content. Do not spam or impersonate another player.")}</p><h2>${t("Copyright")}</h2><p>${t("Upload only material you own or are authorized to use, including music. Recording gameplay does not automatically grant rights to every game asset or soundtrack. Check the publisher’s sharing rules. Rights holders can submit a request below without an account.")}</p>${link("/terms", "Terms of Service", "text-link")} · ${link("/prohibited-items", "Prohibited Items", "text-link")}</section><section class="panel prose"><h2>${t("Privacy")}</h2><p>${t("Choose Public, Followers only or Only me for each post. Drafts and saved posts are private. Public posts may be viewed without signing in. Signed media links expire within five minutes; already downloaded copies cannot be recalled.")}</p><p>${t("Captions and resized image or video frames are sent to OpenAI for safety analysis when publishing or changing a profile cover. Video frames are sampled about once per second; audio is not analysed. Automated checks can make mistakes. Report a missed violation or appeal a decision. Contact details in reports remain private. Unused media is removed after seven days.")}</p>${link("#settings", "Privacy & preferences", "btn outline")} ${link("/privacy-policy", "Privacy Policy", "text-link")}<p>${t("Download your account data or request account deletion from Account settings. Data export requires identity confirmation.")}</p>${link("/#account", "My account", "text-link")}<h2>${t("Request a review")}</h2><p>${t("Tell us which post is involved and what should be reviewed. Never include passwords, payment card details or identity documents.")}</p>${link("#request", "Copyright or privacy request", "btn primary full")}${state.user ? link("#submissions", "My submissions & requests", "btn outline full") : ""}</section></div>`;
  }
  async function requestPage(params) {
    const kind = params.get("kind") || "copyright";
    return `${heading("Request a review", "Your contact details are not shown publicly.")}<form id="case-form" class="panel trust-form">${select(
      "Request type",
      "kind",
      [
        ["copyright", "Copyright"],
        ["privacy", "Privacy"],
        ...(state.user
          ? [
              ["appeal", "Appeal"],
              ["comment", "Report comment"],
            ]
          : []),
      ],
      kind,
    )}${field("Post ID", "post_id", params.get("post") || "", "text", 100)}<input type="hidden" name="comment_id" value="${esc(params.get("comment") || "")}">${field("Your name", "name", state.user?.display_name || "", "text", 100)}${field("Contact email", "email", state.user?.email || "", "email", 254)}${field("Original work or supporting reference", "reference", "", "textarea", 1000)}${field("Explain your request", "body", "", "textarea", 4000)}<label class="check"><input type="checkbox" name="attestation" required><span>${t("I confirm this request is accurate and I am the rights holder, affected person or their authorized representative.")}</span></label><p class="form-error" role="alert"></p><button type="submit" class="btn primary">${t("Submit request")}</button><p class="muted">${t("Keep the reference number shown after submission. Support may need additional information to assess the request.")}</p></form>`;
  }
  async function submissionsPage() {
    if (!requireAuth()) return "";
    const r = await api("community/submissions");
    return `${heading("My submissions & requests", "Track reviews and read the reasons for decisions.")}<section class="panel">${r.posts.map((p) => `<article class="report"><span class="tag">${t(p.review_status === "pending" ? "Needs changes" : "Blocked")}</span><h2>${esc(p.title)}</h2><p>${esc(t(p.review_note || "Automatic checks were inconclusive. Edit the content and try again."))}</p>${link("#create/" + p.id, "Edit post", "btn outline")}${p.review_status === "rejected" ? link("#request?kind=appeal&post=" + p.id, "Appeal", "btn outline") : ""}</article>`).join("") || `<p>${t("No pending submissions.")}</p>`}</section><section class="panel"><h2>${t("Your requests")}</h2>${r.cases.map((c) => `<article class="report"><strong>${esc(c.id)}</strong><p>${t(c.kind)} · ${t(c.status)}</p><p>${esc(c.decision)}</p></article>`).join("") || `<p>${t("No requests yet.")}</p>`}</section>`;
  }
  async function reviewQueue() {
    const r = await api("admin/community/queue");
    return `<section class="panel"><h2>${t("Awaiting review")}</h2>${r.posts.map((p) => `<article class="report"><h3>${esc(p.title)}</h3><p>${esc(p.body)}</p><button class="btn outline" data-action="review-post" data-id="${esc(p.id)}">${t("Review submission")}</button></article>`).join("") || `<p>${t("No pending submissions.")}</p>`}</section><section class="panel"><h2>${t("Copyright, privacy & appeals")}</h2>${r.cases.map((c) => `<article class="report"><span class="tag">${esc(t(c.kind))}</span><h3>${esc(c.id)}</h3><p>${esc(c.name)} · ${esc(c.email)}</p><p>${esc(c.reference)}</p><p>${esc(c.body)}</p><p>${t("Post ID")}: ${esc(c.post_id)}</p><button class="btn outline" data-action="review-post" data-id="${esc(c.post_id)}">${t("View post")}</button><form class="case-decision" data-id="${esc(c.id)}">${select("Action", "action", [["resolve", "Resolve request"], ["hide", "Hide post"], ...(c.kind === "comment" ? [["remove_comment", "Remove comment"]] : []), ...(c.kind === "appeal" ? [["reconsider", "Return to review"]] : [])], "resolve")}${field("Decision and reason", "decision", "", "textarea", 1000)}<p class="form-error" role="alert"></p><button type="submit" class="btn primary">${t("Save decision")}</button></form></article>`).join("") || `<p>${t("No requests yet.")}</p>`}</section>`;
  }

  async function render() {
    closeAccountMenu(false);
    const current = ++routeId;
    const [path, query = ""] = location.hash.slice(1).split("?");
    const [page = "discover", id] = path.split("/");
    const params = new URLSearchParams(query);
    composer = null;
    dirty = false;
    if (page === "discover" || !page) filters.game = params.get("game") || "";
    frame(page || "discover");
    document.title = `${t({ u: "Showcase", create: "Create", edit: "Edit profile", settings: "Settings", collection: "Collection", moments: "Moments", moment: "Moment", saved: "Saved", notifications: "Notifications", following: "Following", search: "Search", safety: "Community safety", request: "Request a review", submissions: "My submissions & requests", moderation: "Community moderation", drafts: "Drafts", layout: "Showcase layout", circle: "Your circle", about: "About this player" }[page] || "Discover")} · SentryLoot`;
    window.scrollTo({ top: 0, behavior: "instant" });
    try {
      let html;
      if (page === "collection") html = await collectionPage(id);
      else if (["u", "moments", "about"].includes(page))
        html = await profilePage(page, id, params);
      else if (page === "moment") html = await momentPage(id);
      else if (page === "create") html = await createPage(id);
      else if (page === "edit") html = await editPage();
      else if (page === "settings") html = await settingsPage();
      else if (page === "circle") html = await circlePage(id, params);
      else if (page === "notifications") html = await notificationsPage();
      else if (page === "layout") html = await layoutPage();
      else if (page === "moderation") html = await moderationPage();
      else if (page === "safety") html = await safetyPage();
      else if (page === "request") html = await requestPage(params);
      else if (page === "submissions") html = await submissionsPage();
      else html = await feed(page || "discover", params);
      if (current !== routeId) return;
      $("#view").innerHTML = html;
      bindForms();
      bindGamePills();
      streamPlayers();
      window.SelectMenus?.refresh();
      $("#main").focus({ preventScroll: true });
    } catch (e) {
      if (current !== routeId) return;
      $("#view").innerHTML = empty(
        e.status === 404
          ? "This story is unavailable."
          : "We couldn’t load this page.",
        e.status === 404
          ? "It may be private, removed or unavailable."
          : e.message,
        "retry",
        "Try again",
        "shield",
      );
    }
  }
  function updateLivePreview() {
    const form = $("#composer");
    if (!form || !composer) return;
    const f = new FormData(form);
    const post = {
      ...composer,
      title: f.get("title") || t("Your story starts here."),
      body: f.get("body") || t("A moment worth keeping."),
      game_slug: f.get("game_slug"),
      id: "preview",
      author: state.profile || { ...state.user, handle: "you" },
      reactions: 0,
      comments: 0,
      created_at: new Date().toISOString(),
      media_url: composer.media_url || "",
      thumbnail_url: composer.thumbnail_url || "",
    };
    $("#live-preview").innerHTML = card(post);
    $$("a,button", $("#live-preview")).forEach((e) => {
      e.tabIndex = -1;
      e.removeAttribute("data-action");
      if (e.tagName === "A") e.removeAttribute("href");
    });
  }
  function profilePreview() {
    const f = $("#profile-form");
    if (!f) return;
    const data = new FormData(f);
    $("#profile-preview").innerHTML =
      `<div class="mini-cover ${composer.cover_url ? "" : "abstract-cover"}">${composer.cover_url ? `<img src="${safeURL(composer.cover_url)}" alt="">` : ""}</div>${avatar(state.user, "large")}<h2 data-user-content>${esc(data.get("display_name") || state.user.display_name)}</h2><p>@${esc(data.get("handle") || "your-handle")}</p><p data-user-content>${esc(data.get("bio") || t("A new story on SentryLoot."))}</p>`;
  }
  async function uploadPostFile(file, status) {
    const ticket = await api("community/uploads", {
      method: "POST",
      body: { size: file.size, content_type: file.type },
    });
    if (ticket.direct) {
      const destination = new URL(ticket.upload_url);
      if (
        !state.r2_upload_origin ||
        destination.origin !== state.r2_upload_origin ||
        destination.protocol !== "https:"
      )
        throw Error(t("Invalid upload URL"));
      const result = await fetch(destination.href, {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
        credentials: "omit",
        referrerPolicy: "no-referrer",
      });
      if (!result.ok) throw Error(t("Upload failed. Please try again."));
    } else {
      for (let offset = 0; offset < file.size; offset += 3 * 1024 * 1024) {
        const end = Math.min(offset + 3 * 1024 * 1024, file.size);
        await api(
          "community/uploads/" + ticket.id + "/chunk?offset=" + offset,
          {
            method: "POST",
            body: file.slice(offset, end),
            headers: { "Content-Type": "application/octet-stream" },
          },
        );
        if (status)
          status.textContent =
            t("Uploading") + " " + Math.floor((end / file.size) * 100) + "%";
      }
    }
    if (status) status.textContent = t("Processing media…");
    return api("community/uploads/" + ticket.id + "/complete", {
      method: "POST",
      body: {},
    });
  }
  async function checkPostVideos(data, feedback) {
    for (const media of data.media || []) {
      if (media.content_type !== "video/mp4") continue;
      let done = false;
      while (!done) {
        const result = await api("community/media/" + media.id + "/check", {
          method: "POST",
          body: {
            title: data.title,
            body: data.body,
            permission: data.permission,
          },
        });
        done = result.done;
        if (feedback)
          feedback.textContent =
            t("Checking content safety…") + " " + (result.progress || 0) + "%";
      }
    }
  }
  async function upload(input) {
    if (!requireAuth()) return;
    const isPost = input.id === "post-media",
      files = Array.from(input.files || []);
    if (!files.length) return;
    if (
      isPost &&
      files.some((f) => f.type.startsWith("video/")) &&
      files.length !== 1
    ) {
      toast(t("Choose multiple images or a single video, not both."));
      input.value = "";
      return;
    }
    if (!isPost && files.some((f) => f.size > 4 * 1024 * 1024)) {
      toast(t("Choose a file up to 4 MB."));
      input.value = "";
      return;
    }
    const draft = composer;
    uploading++;
    const form = input.closest("form"),
      zone = input.closest(".field"),
      status = zone?.querySelector(".upload-status"),
      buttons = $$("button[type=submit],.remove-upload", form);
    buttons.forEach((b) => (b.disabled = true));
    input.disabled = true;
    try {
      for (let index = 0; index < files.length; index++) {
        const file = files[index];
        if (status)
          status.textContent =
            t("Uploading and checking your file…") +
            (files.length > 1 ? ` ${index + 1}/${files.length}` : "");
        if (input.id === "profile-avatar") {
          await api("profile/avatar", {
            method: "POST",
            body: file,
            headers: { "Content-Type": file.type },
          });
          await refresh();
          profilePreview();
          toast(t("Profile picture updated."));
          continue;
        }
        const result = isPost
          ? await uploadPostFile(file, status)
          : await api("community/media", {
              method: "POST",
              body: file,
              headers: { "Content-Type": file.type },
            });
        if (draft !== composer) return;
        if (isPost) {
          if (
            result.content_type.startsWith("video/") ||
            composerMedia().some((m) => m.content_type.startsWith("video/"))
          )
            composer.media = [];
          composer.media.push({
            id: result.id,
            url: result.url,
            content_type: result.content_type,
          });
          syncComposerMedia();
          renderMediaPreviews();
          $$(".remove-upload", form).forEach((b) => (b.disabled = true));
        } else {
          Object.assign(composer, {
            cover_id: result.id,
            cover_url: result.url,
          });
          const container = input.closest(".upload-zone");
          container.querySelector("img")?.remove();
          container.querySelector(".upload-icon")?.remove();
          const image = document.createElement("img");
          image.src = result.url;
          image.alt = "";
          container.prepend(image);
          container.classList.add("has-media");
          container.querySelector("strong").textContent = t("Replace media");
          profilePreview();
        }
        dirty = true;
      }
      if (status) status.textContent = t("Upload complete");
    } catch (e) {
      if (status) status.textContent = t("Upload failed. Please try again.");
      toast(e.message);
    } finally {
      uploading--;
      input.disabled = false;
      $$("button[type=submit],.remove-upload", form).forEach(
        (b) => (b.disabled = false),
      );
      input.value = "";
    }
  }
  function albumViewer(p) {
    return `<div class="album-viewer" data-gallery data-index="0" role="group" aria-label="${t("Photo album")}" tabindex="0">${p.media.map((m, i) => `<img src="${safeURL(m.url)}" alt="${esc(p.title)} · ${i + 1}" data-album-image ${i ? 'hidden loading="lazy"' : ""} decoding="async">`).join("")}<button class="album-arrow album-prev" type="button" data-action="album-prev" aria-label="${t("Previous image")}">‹</button><button class="album-arrow album-next" type="button" data-action="album-next" aria-label="${t("Next image")}">›</button><span class="album-counter" aria-live="polite">1 / ${p.media.length}</span></div>`;
  }
  function moveAlbum(root, index) {
    const images = $$("[data-album-image]", root);
    index = (index + images.length) % images.length;
    root.dataset.index = index;
    images.forEach((img, i) => (img.hidden = i !== index));
    $(".album-counter", root).textContent = `${index + 1} / ${images.length}`;
  }

  function bindForms() {
    $$("[data-gallery]").forEach(
      (root) =>
        (root.onkeydown = (e) => {
          if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
            e.preventDefault();
            moveAlbum(
              root,
              Number(root.dataset.index) + (e.key === "ArrowRight" ? 1 : -1),
            );
          }
        }),
    );
    const request = $("#case-form");
    if (request)
      request.onsubmit = async (e) => {
        e.preventDefault();
        await submit(request, async () => {
          const f = new FormData(request);
          const r = await api("community/cases", {
            method: "POST",
            body: {
              ...Object.fromEntries(f),
              attestation: f.has("attestation"),
            },
          });
          request.innerHTML = `<h2>${t("Request received")}</h2><p>${t("Reference number")}: <strong>${esc(r.id)}</strong></p>${link("#safety", "Safety & rights", "btn outline")}`;
        });
      };
    $$(".case-decision").forEach(
      (form) =>
        (form.onsubmit = async (e) => {
          e.preventDefault();
          await submit(form, async () => {
            await api("admin/community/cases/" + form.dataset.id, {
              method: "POST",
              body: Object.fromEntries(new FormData(form)),
            });
            await render();
          });
        }),
    );

    $$("[data-upload]").forEach(
      (input) => (input.onchange = () => upload(input)),
    );
    const cf = $("#composer");
    if (cf) {
      updateLivePreview();
      cf.oninput = () => {
        dirty = true;
        updateLivePreview();
      };
      cf.onsubmit = async (e) => {
        e.preventDefault();
        const f = new FormData(cf);
        const data = {
          ...composer,
          listing_id: f.get("listing_id") || null,
          title: f.get("title"),
          body: f.get("body"),
          game_slug: f.get("game_slug"),
          audience: f.get("audience"),
          comments_enabled: f.has("comments_enabled"),
          pinned: f.has("pinned"),
          permission: f.has("permission"),
          linked_items: f.getAll("linked_items"),
          status: e.submitter?.value || "draft",
        };
        await submit(cf, async () => {
          if (uploading)
            throw Error(t("Wait for your upload to finish before leaving."));
          if (
            composer.media_type === "video/stream" &&
            data.status === "published"
          ) {
            const check = await api(
              "community/video-upload/" + composer.media_id,
            );
            if (check.state !== "ready")
              throw Error(
                t(
                  check.state === "error"
                    ? "Video processing failed. Choose another file."
                    : "Video is still processing. Save a draft and try again shortly.",
                ),
              );
          }
          const feedback = $("[data-safety-status]", cf);
          if (feedback && data.status === "published") {
            feedback.textContent = t("Checking content safety…");
            await checkPostVideos(data, feedback);
          }
          const p = await api(
            "community/posts" + (composer.id ? "/" + composer.id : ""),
            { method: composer.id ? "PATCH" : "POST", body: data },
          );
          dirty = false;
          await refresh();
          location.hash = ["pending", "rejected"].includes(p.review_status)
            ? "submissions"
            : p.status === "draft"
              ? "drafts"
              : "moment/" + p.id;
          toast(
            t(
              p.review_status === "rejected"
                ? p.review_note
                : p.review_status === "pending"
                  ? "Automatic checks were inconclusive. Edit the content and try again."
                  : p.status === "draft"
                    ? "Draft saved."
                    : "Your story is published.",
            ),
          );
        });
      };
    }
    const pf = $("#profile-form");
    if (pf) {
      profilePreview();
      pf.oninput = () => {
        dirty = true;
        profilePreview();
      };
      pf.onsubmit = async (e) => {
        e.preventDefault();
        const f = new FormData(pf);
        await submit(pf, async () => {
          await api("community/profile", {
            method: "PATCH",
            body: {
              display_name: f.get("display_name"),
              handle: f.get("handle"),
              bio: f.get("bio"),
              ...(composer.cover_id ? { cover_id: composer.cover_id } : {}),
            },
          });
          dirty = false;
          await refresh();
          location.hash = meRoute();
          toast(t("Profile updated."));
        });
      };
    }
    const sf = $("#settings-form");
    if (sf)
      sf.onsubmit = async (e) => {
        e.preventDefault();
        const f = new FormData(sf);
        await submit(sf, async () => {
          await api("community/profile", {
            method: "PATCH",
            body: {
              visibility: f.get("visibility"),
              preferences: {
                show_country: f.has("show_country"),
                comments: f.get("comments"),
                games: f.getAll("games"),
                notify_follow: f.has("notify_follow"),
                notify_comment: f.has("notify_comment"),
                notify_reaction: f.has("notify_reaction"),
              },
            },
          });
          await refresh();
          toast(t("Preferences saved."));
        });
      };
    const lf = $("#layout-form");
    if (lf) {
      let dragged = null;
      $$("[data-pin]", lf).forEach((row) => {
        row.ondragstart = (e) => {
          dragged = row;
          e.dataTransfer.effectAllowed = "move";
          row.classList.add("dragging");
        };
        row.ondragend = () => row.classList.remove("dragging");
        row.ondragover = (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        };
        row.ondrop = (e) => {
          e.preventDefault();
          if (dragged && dragged !== row) row.before(dragged);
        };
      });
    }
    if (lf)
      lf.onsubmit = async (e) => {
        e.preventDefault();
        const pins = $$("input[name=pins]:checked", lf).map((e) => e.value);
        await submit(lf, async () => {
          await api("community/profile", {
            method: "PATCH",
            body: { layout: pins },
          });
          await refresh();
          toast(t("Showcase layout saved."));
        });
      };
    const comments = $("#comment-form");
    if (comments)
      comments.onsubmit = async (e) => {
        e.preventDefault();
        if (!requireAuth()) return;
        await submit(comments, async () => {
          await api("community/posts/" + comments.dataset.post + "/comments", {
            method: "POST",
            body: { body: new FormData(comments).get("body") },
          });
          await render();
          toast(t("Comment posted."));
        });
      };
  }
  async function submit(form, fn) {
    const error = $(".form-error", form);
    if (error) error.textContent = "";
    const buttons = $$("button[type=submit]", form);
    buttons.forEach((b) => (b.disabled = true));
    try {
      await fn();
    } catch (e) {
      if (error) error.textContent = t(e.message);
      else toast(e.message);
    } finally {
      buttons.forEach((b) => (b.disabled = false));
      const feedback = $("[data-safety-status]", form);
      if (feedback) feedback.textContent = "";
    }
  }
  function share(id, profile = false) {
    const url = new URL(
      "/community#" + (profile ? "u/" : "moment/") + id,
      location.origin,
    ).href;
    modal(
      "Share this story",
      `<p>${t("A good story deserves good company.")}</p><label class="field"><span>${t("Link")}</span><input id="share-url" readonly value="${esc(url)}"></label>${button("Copy link", "copy", "primary full")}`,
    );
  }
  async function action(el) {
    if (el.dataset.action === "account-menu") {
      if (!$("#profile-menu-root").hidden) {
        closeAccountMenu();
        return;
      }
      await openAccountMenu();
      return;
    }
    if (el.dataset.action === "logout") {
      if (dirty || uploading) {
        toast(t("Save your changes before leaving."));
        return;
      }
      el.disabled = true;
      await accountLogout();
      return;
    }
    if (el.dataset.action === "link-facebook") {
      if (dirty || uploading) {
        toast(t("Save your changes before leaving."));
        return;
      }
      const r = await api("oauth/start", {
        method: "POST",
        body: {
          provider: "facebook",
          mode: "link",
          country: state.user?.country || "UZ",
        },
      });
      location.assign(r.authorization_url);
      return;
    }

    const a = el.dataset.action,
      id = el.dataset.id;
    if (a === "review-post") {
      const p = await api("admin/community/review/" + id);
      modal(
        "Review submission",
        `<div class="prose"><h3>${esc(p.title)}</h3><p>${esc(p.body)}</p>${listingPanel(p)}${p.media_type === "video/stream" ? `<div class="stream-player" data-stream="${safeURL(p.media_url)}"></div>` : p.media_type === "video/mp4" ? `<video class="review-media" controls src="${safeURL(p.media_url)}"></video>` : p.media?.map((m) => `<img class="review-media" src="${safeURL(m.url)}" alt="">`).join("") || ""}</div><form id="review-form">${select(
          "Decision",
          "decision",
          [
            ["approved", "Approve"],
            ["rejected", "Remove"],
          ],
          "approved",
        )}${field("Decision and reason", "note", "", "textarea", 1000)}<p class="form-error" role="alert"></p><button class="btn primary" type="submit">${t("Save decision")}</button></form>`,
        true,
      );
      $("#review-form").onsubmit = async (e) => {
        e.preventDefault();
        await submit(e.target, async () => {
          await api("admin/community/review/" + id, {
            method: "POST",
            body: {
              ...Object.fromEntries(new FormData(e.target)),
              review_token: p.review_token,
            },
          });
          dialog.close();
          await render();
        });
      };
      streamPlayers(dialog);
      window.SelectMenus?.refresh();
      return;
    }

    if (a === "game-pill") {
      const game = el.dataset.game;
      const selected = game && filters.game !== game ? game : "";
      location.hash =
        "discover" + (selected ? "?game=" + encodeURIComponent(selected) : "");
      return;
    }
    if (a === "scroll-games") {
      const row = $(".game-pills-scroll");
      row?.scrollBy({
        left:
          Number(el.dataset.direction) * Math.max(160, row.clientWidth * 0.7),
        behavior: matchMedia("(prefers-reduced-motion:reduce)").matches
          ? "instant"
          : "smooth",
      });
      return;
    }
    if (a === "stay") {
      dialog.close();
      return;
    }
    if (a === "leave") {
      dirty = false;
      dialog.close();
      location.href = pendingLink;
      return;
    }
    if (a === "collection-create") {
      if (requireAuth()) location.hash = "create?kind=item";
      return;
    }
    if (a === "select-item") {
      const p = activePosts.find((p) => p.id === id);
      if (p) {
        $("#item-inspector").innerHTML = collectionInspector(p);
        $$(".collection-tile").forEach((b) =>
          b.classList.toggle("selected", b.dataset.id === id),
        );
        if (innerWidth < 1080)
          $("#item-inspector").scrollIntoView({
            behavior: matchMedia("(prefers-reduced-motion:reduce)").matches
              ? "instant"
              : "smooth",
            block: "start",
          });
      }
      return;
    }
    if (a === "more-items") {
      el.disabled = true;
      const r = await api(
        "community/posts?" +
          queryString({
            user: el.dataset.user,
            kind: "item",
            game: filters.game,
            offset: el.dataset.offset,
          }),
      );
      activePosts.push(...r.posts);
      $(".collection-tiles").insertAdjacentHTML(
        "beforeend",
        r.posts
          .map(
            (item) =>
              `<button class="collection-tile" data-action="select-item" data-id="${item.id}">${item.media_type?.startsWith("image/") ? `<img src="${safeURL(item.thumbnail_url || item.media_url)}" alt="">` : icon("gem")}<span><small>${esc(gameName(item.game_slug))}</small><strong>${esc(item.title)}</strong></span></button>`,
          )
          .join(""),
      );
      if (r.next === null) el.remove();
      else {
        el.dataset.offset = r.next;
        el.disabled = false;
      }
      return;
    }
    if (a === "remove-upload") {
      if (!uploading && composer) {
        composer.media = composerMedia().filter((m) => m.id !== id);
        syncComposerMedia();
        dirty = true;
        renderMediaPreviews();
      }
      return;
    }
    if (a === "album-prev" || a === "album-next") {
      const root = el.closest("[data-gallery]");
      if (root)
        moveAlbum(
          root,
          Number(root.dataset.index) + (a === "album-next" ? 1 : -1),
        );
      return;
    }
    if (a === "create") {
      if (requireAuth()) location.hash = "create";
      return;
    }
    if (a === "edit") {
      if (requireAuth()) location.hash = "edit";
      return;
    }
    if (a === "retry") {
      await refresh();
      await render();
      return;
    }
    if (a === "find-players") {
      location.hash = "search";
      return;
    }
    if (a === "share" || a === "share-profile") {
      share(id, a === "share-profile");
      return;
    }
    if (a === "copy") {
      const input = $("#share-url");
      try {
        await navigator.clipboard.writeText(input.value);
        toast(t("Link copied."));
      } catch {
        input.focus();
        input.select();
        toast(t("Select and copy this link."));
      }
      return;
    }
    if (a === "post-menu") {
      const p = activePosts.find((p) => p.id === id);
      modal(
        "Post options",
        `<div class="dialog-options">${button("Share", "share", "full").replace('data-action="share"', `data-action="share" data-id="${id}"`)}${p?.owner ? link("#create/" + id, "Edit post", "btn full") + `<button class="btn danger full" data-action="confirm-delete" data-id="${id}">${t("Delete post")}</button>` : `<button class="btn full" data-action="report:${id}">${t("Report this post")}</button><button class="btn danger full" data-action="confirm-block" data-id="${p?.author.id}">${t("Block player")}</button>`}</div>`,
      );
      return;
    }
    if (a === "confirm-delete") {
      modal(
        "Delete this post?",
        `<p>${t("This removes the post, reactions and comments. This cannot be undone.")}</p><button class="btn danger full" data-action="delete" data-id="${id}">${t("Delete post")}</button>`,
      );
      return;
    }
    if (a === "confirm-block") {
      modal(
        "Block this player?",
        `<p>${t("They will no longer be able to view your posts or interact with you.")}</p><button class="btn danger full" data-action="block" data-id="${id}">${t("Block player")}</button>`,
      );
      return;
    }
    if (a.startsWith("report:")) {
      if (!requireAuth()) return;
      const pid = a.split(":")[1];
      modal(
        "Report this post",
        `<form id="report-form">${select(
          "Reason",
          "reason",
          [
            ["spam", "Spam"],
            ["harassment", "Harassment"],
            ["copyright", "Copyright"],
            ["unsafe", "Unsafe content"],
            ["other", "Other"],
          ],
          "spam",
        )}${field("Additional details", "body", "", "textarea", 1000)}<p class="form-error" role="alert"></p><button class="btn primary full" type="submit">${t("Submit report")}</button></form>`,
      );
      $("#report-form").onsubmit = async (e) => {
        e.preventDefault();
        await submit(e.target, async () => {
          await api("community/posts/" + pid + "/report", {
            method: "POST",
            body: Object.fromEntries(new FormData(e.target)),
          });
          dialog.close();
          toast(t("Report received. A moderator will review it."));
        });
      };
      window.SelectMenus?.refresh();
      return;
    }
    if (a === "move-up" || a === "move-down") {
      const row = el.closest("[data-pin]");
      if (a === "move-up" && row.previousElementSibling)
        row.before(row.previousElementSibling);
      else if (a === "move-down" && row.nextElementSibling)
        row.nextElementSibling.after(row);
      return;
    }
    if (a === "new-folder") {
      if (!requireAuth()) return;
      modal(
        "Create a saved folder",
        `<form id="folder-form">${field("Folder name", "name", "", "text", 40)}<p class="form-error" role="alert"></p><button class="btn primary full" type="submit">${t("Create folder")}</button></form>`,
      );
      $("#folder-form").onsubmit = async (e) => {
        e.preventDefault();
        await submit(e.target, async () => {
          await api("community/folders", {
            method: "POST",
            body: { name: new FormData(e.target).get("name") },
          });
          dialog.close();
          await render();
          toast(t("Folder created."));
        });
      };
      return;
    }
    if (a === "more") {
      el.disabled = true;
      const r = await api(
        "community/posts?" +
          queryString({
            mode: el.dataset.mode || "",
            user: el.dataset.user || "",
            kind: el.dataset.kind || filters.kind,
            game: filters.game,
            q: el.dataset.query || "",
            offset: el.dataset.offset,
            folder: filters.folder,
          }),
      );
      activePosts.push(...r.posts);
      const grid = $("#posts") || $(".post-grid");
      grid.insertAdjacentHTML(
        "beforeend",
        r.posts.map((p) => card(p)).join(""),
      );
      if (r.next === null) el.remove();
      else {
        el.dataset.offset = r.next;
        el.disabled = false;
      }
      return;
    }
    if (!requireAuth()) return;
    el.disabled = true;
    try {
      if (a === "like" || a === "save") {
        const p = activePosts.find((p) => p.id === id);
        if (!p) return;
        const property = a === "like" ? "liked" : "saved",
          enabled = !p[property];
        let folder = "Favorites";
        if (a === "save" && enabled) {
          modal(
            "Save to your collection",
            `<form id="save-form">${field("Folder name", "folder", "Favorites", "text", 40)}<p class="muted">${t("Only you can see your saved posts.")}</p><p class="form-error" role="alert"></p><button class="btn primary full" type="submit">${t("Save")}</button></form>`,
          );
          $("#save-form").onsubmit = async (e) => {
            e.preventDefault();
            await submit(e.target, async () => {
              folder = new FormData(e.target).get("folder");
              await api("community/posts/" + id + "/save", {
                method: "POST",
                body: { enabled: true, folder },
              });
              p.saved = true;
              dialog.close();
              await render();
              toast(t("Saved to your collection."));
            });
          };
          return;
        }
        await api("community/posts/" + id + "/" + a, {
          method: "POST",
          body: { enabled, folder },
        });
        p[property] = enabled;
        if (a === "like") p.reactions += enabled ? 1 : -1;
        el.setAttribute("aria-pressed", enabled);
        if (a === "like") {
          const count = el.querySelector("span");
          if (count) count.textContent = p.reactions;
          else await render();
        } else if (location.hash === "#saved") await render();
        toast(t(a === "like" ? "Reaction updated." : "Removed from saved."));
      } else if (["follow", "squad", "block", "unblock"].includes(a)) {
        await api(
          "community/profiles/" + id + "/" + (a === "unblock" ? "block" : a),
          {
            method: "POST",
            body: {
              enabled:
                a === "block"
                  ? true
                  : a === "unblock"
                    ? false
                    : el.dataset.enabled === "true",
            },
          },
        );
        if (dialog.open) dialog.close();
        await refresh();
        await render();
        toast(
          t(
            a === "block"
              ? "Player blocked."
              : a === "unblock"
                ? "Player unblocked."
                : "Your circle is updated.",
          ),
        );
      } else if (a === "delete") {
        await api("community/posts/" + id, { method: "DELETE" });
        dialog.close();
        location.hash = meRoute();
        toast(t("Post deleted."));
      } else if (a === "delete-comment") {
        await api("community/comments/" + id, { method: "DELETE" });
        await render();
      } else if (a === "read-all") {
        await api("community/notifications/read", { method: "POST", body: {} });
        await refresh();
        await render();
      } else if (a === "moderate") {
        await api("admin/community/reports/" + id, {
          method: "POST",
          body: { action: el.dataset.moderation },
        });
        await render();
        toast(t("Moderation action saved."));
      }
    } finally {
      el.disabled = false;
    }
  }
  document.addEventListener("click", async (e) => {
    if (e.target.closest("[data-profile-close]")) {
      e.preventDefault();
      closeAccountMenu();
      return;
    }
    if (e.target.closest("[data-open-support-chat]")) {
      e.preventDefault();
      if (dirty || uploading) {
        toast(t("Save your changes before leaving."));
        return;
      }
      location.assign("/contact?open_chat=1");
      return;
    }

    const navigation = e.target.closest("a[href]");
    if (
      navigation &&
      navigation.getAttribute("href") !== "#main" &&
      (dirty || uploading)
    ) {
      e.preventDefault();
      pendingLink = navigation.href;
      modal(
        uploading ? "Upload in progress" : "Unsaved changes",
        `<p>${t(uploading ? "Wait for your upload to finish before leaving." : "Your latest changes have not been saved. Save a draft or continue editing to keep them.")}</p>${button("Keep editing", "stay", "primary full")}${!uploading ? button("Leave without saving", "leave", "outline full") : ""}`,
      );
      return;
    }
    if (e.target.closest(".skip")) {
      e.preventDefault();
      $("#main")?.focus();
      return;
    }
    const compose = e.target.closest("[data-compose-kind]");
    if (compose) {
      composer.kind = compose.dataset.composeKind;
      $$("[data-compose-kind]").forEach((el) =>
        el.classList.toggle("selected", el === compose),
      );
      updateLivePreview();
      return;
    }
    const f = e.target.closest("[data-filter]");
    if (f) {
      filters[f.dataset.filter] = f.dataset.value;
      await render();
      return;
    }
    const el = e.target.closest("[data-action]");
    if (el) {
      e.preventDefault();
      try {
        await action(el);
      } catch (error) {
        toast(error.message);
        el.disabled = false;
      }
    }
    if (e.target.closest('a[href^="#"]') && dialog.open) dialog.close();
  });
  document.addEventListener(
    "error",
    (e) => {
      if (e.target?.matches?.("img[data-seller-avatar]")) e.target.remove();
    },
    true,
  );
  document.addEventListener("keydown", (e) => {
    const root = $("#profile-menu-root");
    if (root.hidden) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeAccountMenu();
      return;
    }
    if (e.key === "Tab") {
      const items = $$("a[href],button:not([disabled])", root).filter(
        (el) => !el.matches(".profile-backdrop"),
      );
      if (!items.length) return;
      const first = items[0],
        last = items.at(-1);
      if (
        e.shiftKey &&
        (document.activeElement === first ||
          document.activeElement?.id === "profile-dropdown")
      ) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || dirty || uploading) return;
    try {
      await refresh();
      const button = $("#account-button");
      if (!state.user || !button) {
        await render();
        return;
      }
      button.innerHTML = window.SentryLootAccount.avatar(
        state.user.display_name || state.user.email,
        state.user.avatar_url,
        "account-avatar",
        state.user.id,
      );
      if (!$("#profile-menu-root").hidden) await openAccountMenu();
    } catch {}
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-game]")) {
      filters.game = e.target.value;
      render();
    }
  });
  window.addEventListener("hashchange", () => {
    filters = { kind: "", game: "", mode: "", folder: "" };
    render();
  });
  window.addEventListener("storage", async (e) => {
    if (["sentryloot-region-v1", "bozor-language"].includes(e.key) && !dirty) {
      try {
        lang = window.CommunityI18n.language(state.user);
        await refresh();
        await render();
      } catch {}
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      )
        dialog.close();
    }
  });
  async function start() {
    try {
      await refresh();
      if (!["en", "uz", "ru"].includes(lang)) {
        try {
          const response = await fetch("/static/regional-languages.json", {
            signal: AbortSignal.timeout(6000),
          });
          if (response.ok)
            window.SENTRYLOOT_LANGUAGE_DATA = await response.json();
        } catch {}
      }
      syncLanguage();
      await render();
    } catch (e) {
      shell.innerHTML = empty(
        "We couldn’t load this page.",
        e.message,
        "retry",
        "Try again",
      );
    }
  }
  start();
})();
