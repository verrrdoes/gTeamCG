(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const RANK = { action: 0, pending: 1, approved: 2 };
  const BADGE = { approved: ["Approved", "check"], pending: ["Pending", "clock"], action: ["Needs action", "alert"] };
  const DASH_LABEL = { approved: "Approved", pending: "Pending", action: "Need Action" };
  const WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
  const VIEWS = ["dashboard", "requirements", "status"];
  const TITLES = { dashboard: "Dashboard", requirements: "My Requirements", status: "Clearance Status" };
  let data = null;

  // ------------------------------------------------------------ api
  async function api(path, body) {
    const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    const res = await fetch(path, opts);
    if (res.status === 401) {
      location.href = "/";
      throw new Error("Signed out");
    }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
  }

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove("show"), 3200);
  }

  // ------------------------------------------------------------ derived numbers
  function derive() {
    const items = [...data.items].sort((a, b) => RANK[a.status] - RANK[b.status] || a.id - b.id);
    const total = items.length;
    const done = items.filter((i) => i.status === "approved").length;
    return {
      items,
      total,
      done,
      pct: total ? Math.round((done / total) * 100) : 0,
      outstanding: items.filter((i) => i.status !== "approved"),
      pending: items.filter((i) => i.status === "pending").length,
      action: items.filter((i) => i.status === "action").length,
    };
  }

  const badge = (st) => `<span class="badge b-${st}">${ICONS[BADGE[st][1]]}${BADGE[st][0]}</span>`;
  const subtitle = () => `${esc(data.student.name)} &middot; ${esc(data.student.course_year)} &middot; ${esc(data.student.academic_year)}`;
  const s = (txt) => esc(txt).toLowerCase();

  // ------------------------------------------------------------ views
  function dashboardView(d) {
    const first = esc(data.student.name.split(" ")[0]);
    const f = d.outstanding[0];
    let action;
    if (f) {
      action = `<div class="action-head"><span class="warn" ${f.status === "pending" ? 'style="background:#d4a017"' : ""}>!</span>
          <b>${f.status === "action" ? "Action needed" : "Waiting on"}: ${esc(f.office)}</b></div>
        <div class="action-row">
          <button class="btn-primary" data-details="${f.id}">View Details</button>
          <button class="btn-text" data-contact="${f.id}">${ICONS.phone}Contact Office</button>
        </div>`;
    } else {
      action = `<div class="action-head"><span class="warn ok">${ICONS.check}</span><b>All offices have cleared you</b></div>
        <p class="page-sub" style="color:#64748b">Nothing left to do. You can enroll next semester.</p>`;
    }
    const cards = data.items.map((it) => `
      <article class="card office" data-search="${s(it.office + " " + it.summary + " " + DASH_LABEL[it.status])}">
        <span class="badge b-soft-${it.status}">${DASH_LABEL[it.status]}</span>
        <h3>${esc(it.office)}</h3>
        <p>${esc(it.summary)}</p>
      </article>`).join("");
    return `
      <div class="page-head"><h1 class="page-title">Good day, ${first}</h1><span class="pill">Student clearance portal</span></div>
      <div class="grid-2">
        <section class="card overall" data-search="overall clearance done">
          <div class="top"><span>Overall Clearance</span><span class="pill soft">${d.done} of ${d.total} offices</span></div>
          <p class="big">You&rsquo;re<br>${d.pct}% Done</p>
          <div class="bar" role="progressbar" aria-valuenow="${d.pct}" aria-valuemin="0" aria-valuemax="100"><i style="--w:${d.pct}%"></i></div>
          <p class="foot">${d.done} of ${d.total} offices done</p>
        </section>
        <section class="card action" data-search="action needed contact">${action}</section>
      </div>
      <div class="section-head"><h2>Clearance by office</h2><a href="#/requirements">View all Requirements</a></div>
      <div class="offices">${cards}</div>`;
  }

  function requirementsView(d) {
    const rows = d.items.map((it) => {
      const cls = it.status === "action" ? "btn-primary" : it.status === "pending" ? "btn-outline" : "btn-ghost";
      return `
      <div class="req ${it.status !== "approved" ? "req-warm" : ""}" data-search="${s(it.office + " " + it.title + " " + it.description)}">
        <span class="tile t-${it.status}">${ICONS[it.icon] || ""}</span>
        <div class="req-main">
          <div class="req-top"><b>${esc(it.title)}</b>${badge(it.status)}</div>
          <p>${esc(it.description)}</p>
        </div>
        <button class="${cls}" data-details="${it.id}">View Details ${ICONS.arrow}</button>
      </div>`;
    }).join("");
    const out = d.outstanding.length;
    return `
      <div class="page-head">
        <div><h1 class="page-title strong">My Requirements</h1><p class="page-sub">${subtitle()}</p></div>
        <span class="pill">Student clearance portal</span>
      </div>
      <div class="section-line">
        <div><h2>Requirements to complete</h2><p>Focus on the tasks you still need to finish before enrollment opens.</p></div>
        <span class="pill gray">${out} ${out === 1 ? "task" : "tasks"} remaining</span>
      </div>
      <div class="req-layout">
        <section class="card checklist">
          <div class="head"><div><h3>Requirement checklist</h3><p>These are the actions that still need your attention.</p></div>
            <span class="pill soft">${out} ${out === 1 ? "task" : "tasks"}</span></div>
          ${rows}
        </section>
        <aside class="card snap">
          <div class="top"><span>Completion Snapshot</span><span class="pill soft">${d.done} of ${d.total} offices</span></div>
          <p class="big">${d.done} of ${d.total}<br>offices cleared</p>
          <div class="bar"><i style="--w:${d.pct}%"></i></div>
          <div class="rows">
            <div><span>Cleared</span><b>${d.done} of ${d.total}</b></div>
            <div><span>Pending</span><b>${ICONS.clock}${out}</b></div>
          </div>
          <div class="future"><b>Future eligibility</b>${out ? "Once fully cleared, you can enroll next semester" : "You&rsquo;re fully cleared. You can enroll next semester."}</div>
        </aside>
      </div>`;
  }

  function statusView(d) {
    const out = d.outstanding.length;
    const rows = d.items.map((it) => `
      <tr class="${it.status !== "approved" ? "warm" : ""}" data-search="${s(it.office + " " + it.detail + " " + BADGE[it.status][0])}">
        <td><span class="office-cell"><span class="ico">${ICONS[it.icon] || ""}</span>${esc(it.office)}</span></td>
        <td>${badge(it.status)}</td>
        <td class="${it.status !== "approved" ? "det-strong" : ""}">${esc(it.detail)}</td>
      </tr>`).join("");
    const steps = d.outstanding.map((it, i) => `
      <div class="step" data-search="${s(it.office + " " + it.title + " " + it.description)}">
        <div class="step-top"><span>${esc(it.office)}</span>${badge(it.status)}</div>
        <h4>${esc(it.title)}</h4>
        <p>${esc(it.description)}</p>
        <button class="${i === 0 ? "btn-primary" : "btn-outline"} wide" data-details="${it.id}">View ${esc(it.office)} details ${ICONS.arrow}</button>
      </div>`).join("") || `<div class="empty">Nothing left to do. Every office has cleared your account.</div>`;
    const summary = out
      ? `${WORDS[out] || out} ${out === 1 ? "office still needs" : "offices still need"} to clear your account.`
      : "Every office has cleared your account.";
    return `
      <div class="page-head">
        <div><h1 class="page-title strong">Clearance Status</h1><p class="page-sub">${subtitle()}</p></div>
        <span class="pill">Student clearance portal</span>
      </div>
      <section class="card summary">
        <span class="tile">${ICONS.shield}</span>
        <div class="txt"><b>${d.done} of ${d.total} offices approved</b><small>${summary}</small></div>
        <div class="counts">
          <div><b class="c-green">${d.done}</b><small>Approved offices</small></div>
          <div><b class="c-amber">${d.pending}</b><small>Pending office</small></div>
          <div><b class="c-orange">${d.action}</b><small>Needs action</small></div>
        </div>
      </section>
      <div class="status-layout">
        <section class="card table-card">
          <div class="head"><div><h3>Office status overview</h3><p>All ${WORDS[d.total]?.toLowerCase() || d.total} offices, with outstanding items first.</p></div>
            <span class="pill gray">${d.total} offices</span></div>
          <table><thead><tr><th>OFFICE</th><th>STATUS</th><th>CLEARANCE DETAILS</th></tr></thead><tbody>${rows}</tbody></table>
          <div class="table-foot"><span>${d.done} approved &middot; ${out} outstanding</span><a href="#/requirements">View My Requirements ${ICONS.external}</a></div>
        </section>
        <div>
          <section class="card steps">
            <div class="head"><div><h3>Your next steps</h3><span class="pill soft">${out}</span></div><p>Resolve these to complete clearance.</p></div>
            ${steps}
          </section>
          <section class="card elig">
            <small>${ICONS.lock}Enrollment eligibility</small>
            <b>${out ? "Not yet eligible" : "Eligible to enroll"}</b>
            <p>${out ? `You can enroll next semester only once all ${d.total} offices have cleared you.` : "All offices have cleared you. You can enroll next semester."}</p>
          </section>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ render + routing
  function render() {
    const d = derive();
    $("#view-dashboard").innerHTML = dashboardView(d);
    $("#view-requirements").innerHTML = requirementsView(d);
    $("#view-status").innerHTML = statusView(d);
    $("#bell .dot").hidden = d.outstanding.length === 0;
    applySearch();
  }

  function route() {
    const h = location.hash.replace("#/", "");
    const name = VIEWS.includes(h) ? h : "dashboard";
    VIEWS.forEach((v) => ($("#view-" + v).hidden = v !== name));
    $$(".nav a").forEach((a) => (a.dataset.view === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    document.title = `${TITLES[name]} - ClearGate`;
    $("#search").value = "";
    applySearch();
  }

  function applySearch() {
    const q = $("#search").value.trim().toLowerCase();
    $$("[data-search]").forEach((el) => (el.hidden = q !== "" && !el.dataset.search.includes(q)));
  }

  // ------------------------------------------------------------ details dialog
  function openDetails(id) {
    const it = data.items.find((i) => i.id === Number(id));
    if (!it) return;
    const dlg = $("#detail");
    const label = { action: "Needs action", pending: "Pending", approved: "Approved" }[it.status];
    const next = it.status === "approved"
      ? ""
      : `<div class="next"><b>What to do</b>${esc(it.description)}</div>`;
    dlg.innerHTML = `
      <div class="dlg">
        <div class="top"><span>${esc(it.office)}</span>${badge(it.status)}</div>
        <h3 id="detail-title">${esc(it.title)}</h3>
        <p>${esc(it.status === "approved" ? it.description : it.detail)}</p>
        ${next}
        <p class="meta">${esc(label)} &middot; last updated ${esc(it.updated_at)} UTC</p>
        <div class="btns">
          <button class="btn-outline" data-close>Close</button>
          ${it.status !== "approved" ? `<button class="btn-primary" data-contact="${it.id}">${ICONS.phone}Contact Office</button>` : ""}
        </div>
      </div>`;
    dlg.showModal();
    api("/api/activity", { clearance_id: it.id, action: "view_details" }).catch(() => {});
  }

  function contact(id) {
    const it = data.items.find((i) => i.id === Number(id));
    if (!it) return;
    api("/api/activity", { clearance_id: it.id, action: "contact_office" })
      .then(() => toast(`Contact request for ${it.office} was saved.`))
      .catch(() => toast("Couldn't save that request. Please try again."));
  }

  // ------------------------------------------------------------ events
  document.addEventListener("click", (e) => {
    const t = e.target;
    const det = t.closest("[data-details]");
    const con = t.closest("[data-contact]");
    if (det) return openDetails(det.dataset.details);
    if (con) return contact(con.dataset.contact);
    if (t.closest("[data-close]")) return $("#detail").close();
    if (t === $("#detail")) return $("#detail").close(); // click on backdrop
    if (!t.closest(".user-wrap")) closeMenu();
  });
  window.addEventListener("hashchange", route);
  $("#search").addEventListener("input", applySearch);
  $("#bell").addEventListener("click", () => {
    const n = derive().outstanding.length;
    toast(n ? `${n} ${n === 1 ? "item needs" : "items need"} your attention.` : "You're all caught up.");
  });

  function closeMenu() {
    $("#menu").hidden = true;
    $("#user").setAttribute("aria-expanded", "false");
  }
  $("#user").addEventListener("click", () => {
    const open = $("#menu").hidden;
    $("#menu").hidden = !open;
    $("#user").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeMenu());

  async function logout() {
    try { await api("/api/logout", {}); } catch (_) {}
    location.href = "/";
  }
  $("#logout").addEventListener("click", logout);
  $("#logout2").addEventListener("click", logout);

  // ------------------------------------------------------------ load + live refresh
  async function load() {
    data = await api("/api/clearance");
    $("#uname").textContent = data.student.name;
    $("#avatar").textContent = data.student.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
    render();
  }
  load().then(route).catch(() => {});
  // Pick up changes that offices make in the database while the page is open.
  setInterval(() => { if (!document.hidden && !$("#detail").open) load().catch(() => {}); }, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load().catch(() => {}); });
})();
