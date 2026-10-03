/* Shared line icons. Usage: <span data-icon="bell"></span> or ICONS.bell in templates. */
(function () {
  const s = (p) => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${p}</svg>`;
  const ICONS = {
    checklist: s('<path d="M3.5 6.5l1.8 1.8 3-3.3"/><path d="M3.5 13l1.8 1.8 3-3.3"/><path d="M12 7h8.5M12 13.5h8.5M12 19h8.5"/>'),
    bell: s('<path d="M6 9a6 6 0 1112 0c0 6.5 2.5 8 2.5 8h-17S6 15.500 6 9"/><path d="M10 20.500a2.200 2.200 0 004 0"/>'),
    shield: s('<path d="M12 3l7.500 3v5.500c0 4.800-3.200 8-7.500 9.500-4.300-1.500-7.500-4.700-7.500-9.500V6z"/><path d="M8.500 12l2.500 2.500 4.500-5"/>'),
    dashboard: s('<rect x="3.500" y="3.500" width="7" height="7" rx="1.600"/><rect x="13.500" y="3.500" width="7" height="7" rx="1.600"/><rect x="3.500" y="13.500" width="7" height="7" rx="1.600"/><rect x="13.500" y="13.500" width="7" height="7" rx="1.600"/>'),
    clipboard: s('<rect x="5" y="4.500" width="14" height="16.500" rx="2"/><path d="M9 4.500V3.500h6v1M9 11h6M9 15h6"/>'),
    folder: s('<path d="M3 7.500a2 2 0 012-2h4l2 2h8a2 2 0 012 2V18a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M9 14l2 2 4-4"/>'),
    user: s('<circle cx="12" cy="8" r="3.600"/><path d="M4.500 20c.9-3.800 4-5.600 7.500-5.600s6.600 1.800 7.500 5.600"/>'),
    search: s('<circle cx="11" cy="11" r="6.500"/><path d="M16 16l4.500 4.500"/>'),
    chevron: s('<path d="M6 9l6 6 6-6"/>'),
    arrow: s('<path d="M5 12h14M13 6l6 6-6 6"/>'),
    phone: s('<path d="M5 4h3.500l1.500 4-2 1.500a11 11 0 005 5l1.500-2 4 1.500V18a2 2 0 01-2 2A15 15 0 013 6a2 2 0 012-2z"/>'),
    alert: s('<circle cx="12" cy="12" r="9"/><path d="M12 7.500v5.500M12 16.500v.1"/>'),
    book: s('<path d="M12 6.500C10 5 7 4.500 4 5v13c3-.5 6 0 8 1.500 2-1.500 5-2 8-1.500V5c-3-.5-6 0-8 1.500zM12 6.500v13"/>'),
    wallet: s('<path d="M4 7.500A2.500 2.500 0 016.500 5H18v3"/><rect x="3.500" y="7.500" width="17" height="12" rx="2.500"/><path d="M16 13.500h2.500"/>'),
    files: s('<rect x="8" y="3.500" width="11" height="14" rx="2"/><path d="M5 8v10a2 2 0 002 2h8"/><path d="M11 8h5M11 12h5"/>'),
    heart: s('<path d="M12 20s-7.500-4.600-7.500-10A4.200 4.200 0 0112 7.700 4.200 4.200 0 0119.500 10c0 5.400-7.500 10-7.500 10z"/>'),
    cap: s('<path d="M2.500 9.500L12 5l9.500 4.500L12 14z"/><path d="M6.500 11.800V16c1.500 1.400 3.400 2 5.500 2s4-.6 5.500-2v-4.200"/>'),
    box: s('<path d="M12 3l8 4.200v9.600L12 21l-8-4.200V7.200z"/><path d="M4.300 7.400L12 11.500l7.700-4.100M12 11.500V21"/>'),
    clock: s('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    check: s('<path d="M5 12.500l4.500 4.500L19 7.500"/>'),
    lock: s('<rect x="5" y="10.500" width="14" height="10" rx="2"/><path d="M8 10.500V8a4 4 0 018 0v2.500"/>'),
    external: s('<path d="M7 17L17 7M9 7h8v8"/>'),
  };
  window.ICONS = ICONS;
  window.fillIcons = function (root) {
    (root || document).querySelectorAll("[data-icon]").forEach((el) => {
      el.innerHTML = ICONS[el.dataset.icon] || "";
    });
  };
  window.fillIcons();
})();
