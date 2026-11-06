(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const app = $('#app');
  const mobileMQ = matchMedia('(max-width: 899px)');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const KIND = { litter: 'Littering', spit: 'Spitting' };
  const STATUS = { new: 'New', reviewed: 'Reviewed', noticed: 'Noticed', dismissed: 'Dismissed' };

  const ICON = {
    monitor: '<rect x="3" y="4.5" width="18" height="12.5" rx="3.5"/><path d="M8.5 20.5h7M12 17v3.5"/>',
    cameras: '<rect x="3" y="6.5" width="12.5" height="11" rx="3"/><path d="M15.5 10.5 21 7.5v9l-5.5-3"/>',
    notices: '<path d="M7 3.5h7.5L19 8v11.5a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 19.5v-14A1.5 1.5 0 0 1 7.5 3.5Z"/><path d="M9.5 12.5h6M9.5 16h4"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8"/>',
    mark: '<circle cx="12" cy="12" r="7.5"/><path d="M12 8.2V12l2.4 1.8"/>'
  };
  const svgi = (name, style = '') => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" style="${style}">${ICON[name]}</svg>`;

  const VIEWS = [
    { id: 'monitor', title: 'Monitor' },
    { id: 'cameras', title: 'Cameras' },
    { id: 'notices', title: 'Notices' },
    { id: 'settings', title: 'Settings' }
  ];

  const S = {
    status: null, events: [], notices: [], settings: null,
    seen: new Set(), filter: 'all', q: '', evKey: '', ntKey: null,
    view: 'monitor', openId: null, openFrom: null, busy: false
  };

  /* ---------- api ---------- */
  async function api(path, opts = {}) {
    const init = { ...opts };
    if (opts.body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(opts.body);
    }
    const r = await fetch(path, init);
    if (!r.ok) throw new Error((await r.text()) || r.statusText);
    return (r.headers.get('content-type') || '').includes('application/json') ? r.json() : r.text();
  }

  /* ---------- toast ---------- */
  let toastT;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove('show'), 2600);
  }

  /* ---------- segmented control with a sliding pill ---------- */
  function moveInd(seg) {
    if (!seg) return;
    const b = seg.querySelector('button.on');
    const ind = seg.querySelector('.ind');
    if (!b || !ind) return;
    ind.style.width = b.offsetWidth + 'px';
    ind.style.height = b.offsetHeight + 'px';
    ind.style.transform = `translate(${b.offsetLeft}px, 0)`;
  }
  function refreshSegs() { $$('.seg').forEach(moveInd); }
  function bindSeg(seg, cb) {
    if (!seg) return;
    seg.addEventListener('click', e => {
      const b = e.target.closest('button');
      if (!b || !seg.contains(b) || b.classList.contains('on')) return;
      seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
      moveInd(seg);
      if (cb) cb(b.dataset.v);
    });
  }

  /* ---------- navigation ---------- */
  function renderNav() {
    $('#side').innerHTML =
      `<div class="side-brand"><img class="side-mark" src="/brand/veytrix-mark-black.png" alt=""><b>Veytrix</b></div>` +
      VIEWS.map(v => `<button class="side-item" data-go="${v.id}">${svgi(v.id)}<span>${v.title}</span></button>`).join('');
    $('#tabs').innerHTML = '<span class="tab-ind"></span>' +
      VIEWS.map(v => `<button class="tab" data-go="${v.id}">${svgi(v.id)}<span>${v.title}</span></button>`).join('');
  }
  function moveTabInd() {
    const idx = VIEWS.findIndex(v => v.id === S.view);
    const ind = $('.tab-ind');
    if (ind) ind.style.transform = `translateX(${idx * 100}%)`;
  }
  function setView(id) {
    if (!VIEWS.some(v => v.id === id)) id = 'monitor';
    S.view = id;
    app.dataset.view = id;
    $('#viewTitle').textContent = VIEWS.find(v => v.id === id).title;
    $$('[data-go]').forEach(b => b.classList.toggle('on', b.dataset.go === id));
    if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
    moveTabInd();
    requestAnimationFrame(refreshSegs);
    if (id === 'settings') loadSettings();
    refresh();
  }

  /* ---------- status and banner ---------- */
  function renderStatus() {
    const st = S.status;
    if (!st) return;
    const pill = $('#detectPill');
    const state = !st.detector.ready ? 'nomodel' : st.detection_enabled ? 'on' : 'off';
    pill.dataset.state = state;
    pill.querySelector('span').textContent = { on: 'Detecting', off: 'Paused', nomodel: 'No model' }[state];
    pill.setAttribute('aria-pressed', String(st.detection_enabled));
    const total = st.cameras.length;
    const live = st.cameras.filter(c => c.online).length;
    const n = Object.values(st.counts_24h || {}).reduce((a, b) => a + b, 0);
    $('#viewSub').textContent = `${live} of ${total} ${total === 1 ? 'camera' : 'cameras'} live · ${n} ${n === 1 ? 'event' : 'events'} in 24 h`;
    const msgs = [];
    if (!total) msgs.push('No cameras are set up yet. Add them to cameras.json and restart.');
    if (!st.detector.ready) msgs.push('No detection model is loaded, so nothing is detected yet. Live video still works.');
    const b = $('#banner');
    b.hidden = !msgs.length;
    b.textContent = msgs.join(' ');
  }

  async function toggleDetection() {
    const on = !(S.status && S.status.detection_enabled);
    try {
      S.settings = await api('/api/settings', { method: 'PATCH', body: { detection_enabled: on } });
      await refresh();
      if (S.view === 'settings') renderSettings();
    } catch (e) {
      toast('Could not change detection');
    }
  }

  /* ---------- cameras ---------- */
  function camHTML(c, mode) {
    const id = esc(c.id);
    return `<article class="cam" data-cid="${id}">
      <button class="cam-media" data-cam="${id}" aria-label="Open ${esc(c.name)} full screen">
        <img alt="Live view, ${esc(c.name)}" src="/api/cameras/${id}/stream">
        <span class="cam-state"></span>
      </button>
      <div class="cam-foot">
        <div><div class="t">${esc(c.name)}</div><div class="s">${esc(c.place) || 'No place set'}</div></div>
        ${mode === 'manage' ? `<button class="toggle" role="switch" data-camtg="${id}" aria-label="${esc(c.name)} on or off"></button>` : ''}
      </div>
      <p class="cam-err" hidden></p>
    </article>`;
  }
  function renderCams() {
    const st = S.status;
    if (!st) return;
    const monCams = $('#cams'), camGrid = $('#camGrid');
    const target = S.view === 'monitor' ? monCams : S.view === 'cameras' ? camGrid : null;
    for (const el of [monCams, camGrid]) {
      if (el !== target) { el.innerHTML = ''; el.dataset.sig = ''; }
    }
    if (!target) return;
    const mode = S.view === 'cameras' ? 'manage' : 'watch';
    const sig = mode + st.cameras.map(c => `${c.id}|${c.name}|${c.place}`).join(';');
    if (target.dataset.sig !== sig) {
      target.dataset.sig = sig;
      target.innerHTML = st.cameras.length
        ? st.cameras.map(c => camHTML(c, mode)).join('')
        : '<div class="empty">No cameras are connected yet.</div>';
    }
    $$('.cam', target).forEach(card => {
      const c = st.cameras.find(x => x.id === card.dataset.cid);
      if (!c) return;
      const state = !c.enabled ? 'off' : c.online ? 'live' : 'err';
      const stateEl = card.querySelector('.cam-state');
      stateEl.className = 'cam-state ' + (state === 'live' ? 'live' : state === 'err' ? 'err' : '');
      stateEl.textContent = { live: 'Live', off: 'Off', err: 'Offline' }[state];
      const err = card.querySelector('.cam-err');
      err.hidden = !(c.enabled && !c.online && c.error);
      err.textContent = c.error || '';
      const tg = card.querySelector('[data-camtg]');
      if (tg) tg.setAttribute('aria-checked', String(c.enabled));
    });
  }
  async function toggleCamera(cid) {
    const c = S.status && S.status.cameras.find(x => x.id === cid);
    if (!c) return;
    try {
      S.status = await api(`/api/cameras/${encodeURIComponent(cid)}/enabled`, { method: 'POST', body: { enabled: !c.enabled } });
      renderStatus();
      renderCams();
    } catch (e) {
      toast('Could not change that camera');
    }
  }
  function openCamera(cid, from) {
    const c = S.status && S.status.cameras.find(x => x.id === cid);
    if (!c) return;
    openSheet(`
      <div class="sh-media"><img class="morph" alt="${esc(c.name)} live view" src="/api/cameras/${esc(cid)}/stream"><span class="sh-chip">Faces blurred</span></div>
      <div class="sh-info">
        <div class="kick">${c.enabled ? (c.online ? 'Live' : 'Offline') : 'Off'} · ${esc(c.place) || 'No place set'}</div>
        <h2>${esc(c.name)}</h2>
        <p>${esc(c.error || (c.online ? 'Streaming now. Detection runs on this feed.' : 'Waiting for the camera.'))}</p>
      </div>`, { from });
  }

  /* ---------- event list ---------- */
  function listQuery() {
    const p = new URLSearchParams();
    if (S.filter === 'litter' || S.filter === 'spit') p.set('kind', S.filter);
    if (S.filter === 'open') p.set('status', 'open');
    if (S.q) p.set('q', S.q);
    p.set('limit', '300');
    return p.toString();
  }
  function rowHTML(e, i) {
    const enter = !S.seen.has(e.id);
    return `<button class="row${enter ? ' enter' : ''}" data-id="${esc(e.id)}" style="--d:${Math.min(i, 12) * 40}ms">
      <div class="thumb">${e.photo_url ? `<img loading="lazy" alt="" src="${e.photo_url}">` : ''}<span class="badge">${e.clip_url ? 'Clip' : 'Photo'}</span></div>
      <div class="meta">
        <div class="t">${KIND[e.kind] || e.kind} · ${esc(e.camera_name)}</div>
        <div class="s">${esc(e.place)} · ${e.date} ${e.time}</div>
      </div>
      <div class="end">
        <span class="pill st-${e.status}">${STATUS[e.status] || e.status}</span>
        <span class="conf">${Math.round((e.confidence || 0) * 100)}%</span>
      </div>
    </button>`;
  }
  function emptyText() {
    if (S.q || S.filter !== 'all') return 'Nothing matches this filter.';
    if (!S.status || !S.status.detector.ready) return 'Nothing is detected until a model is loaded.';
    return 'No events yet. Each detection appears here with its photo or clip.';
  }
  function renderList() {
    const key = S.events.map(e => `${e.id}:${e.status}:${e.has_notice ? 1 : 0}`).join('|') + '#' + S.filter + '#' + S.q;
    if (key === S.evKey) return;
    S.evKey = key;
    const list = $('#list');
    if (!S.events.length) {
      list.innerHTML = `<div class="empty">${emptyText()}</div>`;
      return;
    }
    list.innerHTML = S.events.map(rowHTML).join('');
    S.events.forEach(e => S.seen.add(e.id));
  }
  function renderNotices() {
    const key = S.notices.map(e => `${e.id}:${e.notice_at}`).join('|');
    if (key === S.ntKey) return;
    S.ntKey = key;
    const path = S.status ? S.status.paths.outbox : '';
    $('#noticeList').innerHTML =
      `<p class="grp-cap">Each notice is saved with its photo or clip. The folder is in Settings.</p>` +
      (S.notices.length
        ? S.notices.map(rowHTML).join('')
        : '<div class="empty">No notices yet. Open an event and choose Write notice.</div>');
    S.notices.forEach(e => S.seen.add(e.id));
  }

  /* ---------- refresh (polls every 2.5 s) ---------- */
  async function refresh() {
    if (S.busy) return;
    S.busy = true;
    try {
      S.status = await api('/api/status');
      renderStatus();
      renderCams();
      if (S.view === 'settings' && S.settings && !$('#sDet')) renderSettings();
      if (S.view === 'monitor') {
        S.events = await api('/api/events?' + listQuery());
        renderList();
      } else if (S.view === 'notices') {
        S.notices = await api('/api/events?status=noticed&limit=300');
        renderNotices();
      }
      const pill = $('#detectPill');
      if (pill.dataset.state === 'offline') renderStatus();
    } catch (e) {
      const pill = $('#detectPill');
      pill.dataset.state = 'offline';
      pill.querySelector('span').textContent = 'Offline';
    } finally {
      S.busy = false;
    }
  }

  /* ---------- settings ---------- */
  async function loadSettings() {
    try {
      S.settings = await api('/api/settings');
      renderSettings();
    } catch (e) {
      toast('Could not load settings');
    }
  }
  function renderSettings() {
    const st = S.status, s = S.settings;
    if (!st || !s) return;
    const ready = st.detector.ready;
    $('#settingsBody').innerHTML = `
      <div class="grp">
        <div class="grp-row">
          <div><div class="t">Detection</div><div class="s">Look for littering and spitting on every camera that is on</div></div>
          <button class="toggle" id="sDet" role="switch" aria-checked="${s.detection_enabled}" aria-label="Detection"></button>
        </div>
        <div class="grp-row">
          <div><div class="t">Sensitivity</div><div class="s">Higher finds more events and gives more false alarms</div></div>
          <div class="seg" id="sSens">
            <span class="ind"></span>
            ${['low', 'balanced', 'high'].map(v => `<button data-v="${v}" class="${s.sensitivity === v ? 'on' : ''}">${v[0].toUpperCase() + v.slice(1)}</button>`).join('')}
          </div>
        </div>
        <div class="grp-row">
          <div><div class="t">Repeat window</div><div class="s">Shortest gap between two events from the same camera</div></div>
          <div class="stepper">
            <button id="cdMinus" aria-label="Shorter">−</button>
            <b id="cdVal">${s.cooldown_s} s</b>
            <button id="cdPlus" aria-label="Longer">+</button>
          </div>
        </div>
      </div>
      <div class="grp">
        <div class="grp-row">
          <div><div class="t">Detection model</div><div class="s ${ready ? 'mono' : ''}">${esc(ready ? st.detector.path : 'No trained model is installed yet')}</div></div>
          <span class="pill ${ready ? 'st-noticed' : 'st-dismissed'}">${ready ? 'Loaded' : 'Not loaded'}</span>
        </div>
        <div class="grp-row"><div><div class="t">Evidence folder</div><div class="s mono">${esc(st.paths.media)}</div></div></div>
        <div class="grp-row"><div><div class="t">Notice outbox</div><div class="s mono">${esc(st.paths.outbox)}</div></div></div>
      </div>
      <p class="foot">Faces are blurred before a frame is stored or streamed. Nothing is matched to a name, and faces are never compared across cameras.</p>`;
    bindSeg($('#sSens'), v => patchSettings({ sensitivity: v }));
    $('#sDet').addEventListener('click', () => patchSettings({ detection_enabled: !S.settings.detection_enabled }));
    $('#cdMinus').addEventListener('click', () => patchSettings({ cooldown_s: S.settings.cooldown_s - 5 }));
    $('#cdPlus').addEventListener('click', () => patchSettings({ cooldown_s: S.settings.cooldown_s + 5 }));
    requestAnimationFrame(refreshSegs);
  }
  async function patchSettings(body) {
    try {
      S.settings = await api('/api/settings', { method: 'PATCH', body });
      await refresh();
      renderSettings();
    } catch (e) {
      toast('Could not save that setting');
    }
  }

  /* ---------- sheets: morph on desktop, slide up on phones ---------- */
  function useVT() {
    return !mobileMQ.matches && typeof document.startViewTransition === 'function';
  }
  function openSheet(html, opts = {}) {
    const ov = $('#overlay');
    const from = opts.from && opts.from.isConnected ? opts.from : null;
    const apply = () => {
      $('#shBody').innerHTML = html;
      S.openFrom = from;
      const morph = $('#shBody .morph');
      if (morph && from && useVT()) morph.style.viewTransitionName = 'morph';
      ov.classList.add('open');
      ov.setAttribute('aria-hidden', 'false');
      requestAnimationFrame(() => $$('#shBody .seg').forEach(moveInd));
      $('#shClose').focus({ preventScroll: true });
    };
    if (from && useVT()) {
      from.style.viewTransitionName = 'morph';
      document.startViewTransition(() => { from.style.viewTransitionName = ''; apply(); });
    } else {
      apply();
    }
  }
  function closeSheet() {
    const ov = $('#overlay');
    if (!ov.classList.contains('open')) return;
    const from = S.openFrom && S.openFrom.isConnected ? S.openFrom : null;
    const sheet = $('#sheet');
    const apply = () => {
      const m = $('#shBody .morph');
      if (m) m.style.viewTransitionName = '';
      if (from && useVT()) from.style.viewTransitionName = 'morph';
      sheet.style.transform = '';
      $('#scrim').style.opacity = '';
      ov.classList.remove('open');
      ov.setAttribute('aria-hidden', 'true');
      S.openFrom = null;
      S.openId = null;
      clearTimeout(closeSheet.t);
      closeSheet.t = setTimeout(() => {
        if (!ov.classList.contains('open')) $('#shBody').innerHTML = '';
      }, 650);
    };
    if (from && useVT()) {
      const t = document.startViewTransition(apply);
      t.finished.then(() => { from.style.viewTransitionName = ''; });
    } else {
      apply();
    }
  }

  async function openEvent(id, from) {
    let e;
    try {
      e = await api(`/api/events/${encodeURIComponent(id)}`);
    } catch (err) {
      e = S.events.find(x => x.id === id) || S.notices.find(x => x.id === id);
      if (!e) return toast('That event is no longer available');
    }
    let notice = '';
    if (e.has_notice) {
      try { notice = await api(`/api/events/${encodeURIComponent(id)}/notice`); } catch (err) { /* shown as empty */ }
    }
    S.openId = id;
    openSheet(eventHTML(e, notice), { from });
    bindEventSheet(id);
  }
  function eventHTML(e, notice) {
    const media = e.clip_url
      ? `<video class="morph" playsinline preload="metadata" poster="${e.photo_url || ''}" src="${e.clip_url}"></video>
         <div class="vc">
           <button class="vc-play" aria-label="Play clip"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg></button>
           <input class="vc-seek" type="range" min="0" max="1000" value="0" aria-label="Seek">
           <span class="vc-time">0:00</span>
         </div>`
      : `<img class="morph" alt="${KIND[e.kind] || ''} photo" src="${e.photo_url}">`;
    const body = e.has_notice ? esc(notice) : 'No notice yet. Write one to save the notice and its evidence to the outbox folder.';
    return `
      <div class="sh-media">${media}<span class="sh-chip">${e.clip_url ? 'Clip · faces blurred' : 'Photo · faces blurred'}</span></div>
      <div class="sh-info">
        <div class="kick">${KIND[e.kind] || e.kind} · ${esc(e.camera_name)}</div>
        <h2>${esc(e.place)}</h2>
        <p>${e.date} ${e.time} · ${Math.round((e.confidence || 0) * 100)}% confidence · ${esc(e.id)}</p>
      </div>
      <div class="sh-row">
        <div class="seg" id="shStatus">
          <span class="ind"></span>
          ${Object.keys(STATUS).map(k => `<button data-v="${k}" class="${e.status === k ? 'on' : ''}">${STATUS[k]}</button>`).join('')}
        </div>
      </div>
      <div class="sh-actions">
        <button class="btn ghost" id="shDismiss">Dismiss</button>
        <button class="btn primary${e.has_notice ? ' done' : ''}" id="shNotice" ${e.has_notice ? 'disabled' : ''}>
          <svg class="ck" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 8.5l3.8 3.8 7.2-8.6"/></svg>
          <span>${e.has_notice ? 'Written to outbox' : 'Write notice'}</span>
        </button>
      </div>
      <div class="letter"><div class="lh">${e.has_notice ? 'Notice in outbox' : 'Notice'}</div><pre>${body}</pre></div>`;
  }
  function bindVideo(v) {
    const root = v.parentElement;
    const play = root.querySelector('.vc-play');
    const seek = root.querySelector('.vc-seek');
    const time = root.querySelector('.vc-time');
    const fmt = s => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
    const icon = on => on
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1.5"/><rect x="14" y="5" width="4" height="14" rx="1.5"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>';
    play.addEventListener('click', () => { if (v.paused) v.play().catch(() => {}); else v.pause(); });
    v.addEventListener('click', () => play.click());
    v.addEventListener('play', () => { play.innerHTML = icon(true); play.setAttribute('aria-label', 'Pause clip'); });
    v.addEventListener('pause', () => { play.innerHTML = icon(false); play.setAttribute('aria-label', 'Play clip'); });
    v.addEventListener('ended', () => { play.innerHTML = icon(false); play.setAttribute('aria-label', 'Play clip'); });
    v.addEventListener('loadedmetadata', () => { time.textContent = `0:00 / ${fmt(v.duration)}`; });
    v.addEventListener('timeupdate', () => {
      if (v.duration) {
        seek.value = (v.currentTime / v.duration) * 1000;
        seek.style.setProperty('--p', (seek.value / 10) + '%');
      }
      time.textContent = `${fmt(v.currentTime)} / ${fmt(v.duration)}`;
    });
    seek.addEventListener('input', () => { if (v.duration) v.currentTime = (seek.value / 1000) * v.duration; });
  }
  function bindEventSheet(id) {
    const root = $('#shBody');
    const vid = $('video', root);
    if (vid) bindVideo(vid);
    bindSeg($('#shStatus', root), v => setStatus(id, v));
    $('#shDismiss', root).addEventListener('click', () => setStatus(id, 'dismissed'));
    $('#shNotice', root).addEventListener('click', async ev => {
      const b = ev.currentTarget;
      b.disabled = true;
      try {
        await api(`/api/events/${encodeURIComponent(id)}/notice`, { method: 'POST' });
        b.classList.add('done');
        b.querySelector('span').textContent = 'Written to outbox';
        toast('Notice written to the outbox');
        await refresh();
      } catch (err) {
        b.disabled = false;
        toast('Could not write the notice');
      }
    });
  }
  async function setStatus(id, status) {
    try {
      await api(`/api/events/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status } });
      $$('#shStatus button').forEach(b => b.classList.toggle('on', b.dataset.v === status));
      moveInd($('#shStatus'));
      await refresh();
    } catch (err) {
      toast('Could not update that event');
    }
  }

  /* ---------- mobile drag-to-dismiss on the sheet handle ---------- */
  function bindSheetDrag() {
    const sheet = $('#sheet');
    const handle = $('.sh-top', sheet);
    let drag = null;
    handle.addEventListener('pointerdown', e => {
      if (!mobileMQ.matches) return;
      drag = { y: e.clientY, t: performance.now(), dy: 0, v: 0 };
      handle.setPointerCapture(e.pointerId);
      sheet.style.transition = 'none';
    });
    handle.addEventListener('pointermove', e => {
      if (!drag) return;
      const dy = Math.max(0, e.clientY - drag.y);
      const now = performance.now();
      drag.v = (dy - drag.dy) / Math.max(1, now - drag.t);
      drag.t = now;
      drag.dy = dy;
      sheet.style.transform = `translateY(${dy}px)`;
      $('#scrim').style.opacity = String(Math.max(0, 1 - dy / 320));
    });
    const end = () => {
      if (!drag) return;
      const { dy, v } = drag;
      drag = null;
      sheet.style.transition = '';
      if (dy > 110 || v > 0.6) {
        closeSheet();
      } else {
        sheet.style.transform = '';
        $('#scrim').style.opacity = '';
      }
    };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  }

  /* ---------- global delegation ---------- */
  document.addEventListener('click', e => {
    const go = e.target.closest('[data-go]');
    if (go) return setView(go.dataset.go);
    const row = e.target.closest('.row[data-id]');
    if (row) return openEvent(row.dataset.id, row.querySelector('img'));
    const cam = e.target.closest('[data-cam]');
    if (cam) return openCamera(cam.dataset.cam, cam.querySelector('img'));
    const tg = e.target.closest('[data-camtg]');
    if (tg) return toggleCamera(tg.dataset.camtg);
  });

  /* ---------- boot ---------- */
  renderNav();
  bindSeg($('#filt'), v => { S.filter = v; refresh(); });
  $('#detectPill').addEventListener('click', toggleDetection);
  $('#sideBtn').addEventListener('click', () => {
    app.classList.toggle('side-hidden');
    try { localStorage.setItem('cs-side', app.classList.contains('side-hidden') ? '0' : '1'); } catch (_) { /* private mode */ }
    requestAnimationFrame(refreshSegs);
  });
  try { if (localStorage.getItem('cs-side') === '0') app.classList.add('side-hidden'); } catch (_) { /* ignore */ }

  $('#shClose').addEventListener('click', closeSheet);
  $('#scrim').addEventListener('click', closeSheet);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSheet(); });
  bindSheetDrag();

  let qT;
  $('#q').addEventListener('input', e => {
    clearTimeout(qT);
    qT = setTimeout(() => { S.q = e.target.value.trim().toLowerCase(); refresh(); }, 220);
  });

  window.addEventListener('hashchange', () => setView(location.hash.slice(1)));
  window.addEventListener('resize', () => { refreshSegs(); moveTabInd(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(refresh, 2500);

  setView(['monitor', 'cameras', 'notices', 'settings'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'monitor');
})();
