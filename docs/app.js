/* SLP 결과 화면: 검색 결과 보기 + 관심 물건을 GitHub 저장소(favorites.json)에 저장 */
"use strict";

const FAV_PATH = "docs/data/favorites.json";
const STATUSES = ["검토중", "현장답사 예정", "현장답사 완료", "유력", "보류", "제외"];
const SOURCE_NAMES = { onbid: "온비드 공매", court: "법원경매", naver: "네이버 부동산" };
const PYEONG = 3.305785;

const $ = (s) => document.querySelector(s);
const state = { index: [], search: null, favorites: { items: {} }, favSha: null, view: "results", mode: "list", map: null };

/* ---------- 공통 ---------- */
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  try { const x = new URL(u); return x.protocol === "https:" || x.protocol === "http:" ? x.href : ""; } catch { return ""; }
}
function won(manwon) {
  if (manwon == null) return "미상";
  const eok = Math.floor(manwon / 10000), rest = manwon % 10000;
  if (!eok) return `${rest.toLocaleString()}만원`;
  return `${eok}억${rest ? " " + rest.toLocaleString() + "만" : ""}원`;
}
function area(m2) {
  if (!m2) return "미상";
  return `${Math.round(m2).toLocaleString()}㎡ (${(m2 / PYEONG).toFixed(0)}평)`;
}
function toast(msg, ms = 3000) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
function store(key, val) {
  try { if (val === undefined) return localStorage.getItem(key); if (val === null) localStorage.removeItem(key); else localStorage.setItem(key, val); } catch { return null; }
}
function repo() {
  const saved = store("slp.repo");
  if (saved) return saved;
  const host = location.hostname;
  if (host.endsWith(".github.io")) return `${host.split(".")[0]}/${location.pathname.split("/")[1]}`;
  return "oysking55-ctrl/slp";
}
const token = () => store("slp.token") || "";

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

/* ---------- GitHub 저장 (Contents API) ---------- */
function b64encode(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
function b64decode(b64) {
  const bin = atob(b64.replace(/\n/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}
function ghHeaders() {
  const h = { Accept: "application/vnd.github+json" };
  if (token()) h.Authorization = `Bearer ${token()}`;
  return h;
}
async function ghReadFavorites() {
  const r = await fetch(`https://api.github.com/repos/${repo()}/contents/${FAV_PATH}`, { headers: ghHeaders(), cache: "no-store" });
  if (r.status === 404) return { data: { items: {} }, sha: null };
  if (!r.ok) throw new Error(`GitHub 읽기 실패 (${r.status})`);
  const j = await r.json();
  return { data: JSON.parse(b64decode(j.content)), sha: j.sha };
}
async function loadFavorites() {
  try {
    const { data, sha } = await ghReadFavorites();
    state.favorites = data; state.favSha = sha;
  } catch (e) {
    // API 한도 초과 등: Pages에 배포된 사본으로 대신 (조금 늦을 수 있음)
    try { state.favorites = await getJSON("data/favorites.json"); } catch { state.favorites = { items: {} }; }
  }
  state.favorites.items ||= {};
  $("#favCount").textContent = Object.keys(state.favorites.items).length;
}
/** 최신 파일을 다시 읽어 mutate를 적용한 뒤 커밋. 다른 기기에서 바꾼 내용과 충돌하면 재시도. */
async function saveFavorites(mutate, message) {
  if (!token()) { toast("관심 저장에는 GitHub 토큰이 필요합니다. 설정 탭에서 입력해 주세요.", 5000); showView("settings"); return false; }
  for (let attempt = 0; attempt < 3; attempt++) {
    const { data, sha } = await ghReadFavorites();
    data.items ||= {};
    mutate(data);
    data.updated_at = new Date().toISOString();
    const r = await fetch(`https://api.github.com/repos/${repo()}/contents/${FAV_PATH}`, {
      method: "PUT", headers: { ...ghHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ message, content: b64encode(JSON.stringify(data, null, 1) + "\n"), sha: sha || undefined }),
    });
    if (r.ok) {
      state.favorites = data; state.favSha = (await r.json()).content.sha;
      $("#favCount").textContent = Object.keys(data.items).length;
      return true;
    }
    if (r.status !== 409 && r.status !== 422) {
      toast(r.status === 401 || r.status === 403 ? "토큰 권한을 확인해 주세요 (Contents: Read and write)." : `저장 실패 (${r.status})`, 5000);
      return false;
    }
  }
  toast("다른 곳에서 동시에 수정 중이라 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", 5000);
  return false;
}

/* ---------- 검색 결과 ---------- */
async function loadIndex() {
  try { state.index = await getJSON("data/searches/index.json"); } catch { state.index = []; }
  const sel = $("#searchSelect");
  sel.innerHTML = state.index.map((s) =>
    `<option value="${esc(s.id)}">${esc(s.created_at.slice(0, 16).replace("T", " "))} · ${esc(s.title)} (${s.counts.listings}건)</option>`).join("");
  if (!state.index.length) {
    sel.innerHTML = `<option>아직 검색 결과가 없습니다</option>`;
    $("#list").innerHTML = `<div class="empty">상단의 <b>+ 새 검색</b>을 눌러 조건을 고르면, 몇 분 뒤 이곳에 결과가 나타납니다.</div>`;
    return;
  }
  const want = new URLSearchParams(location.hash.slice(1)).get("search");
  sel.value = state.index.some((s) => s.id === want) ? want : state.index[0].id;
  await loadSearch(sel.value);
}

async function loadSearch(id) {
  $("#list").innerHTML = `<div class="empty">불러오는 중…</div>`;
  state.search = await getJSON(`data/searches/${encodeURIComponent(id)}.json`);
  history.replaceState(null, "", `#search=${encodeURIComponent(id)}`);
  renderMeta();
  const types = [...new Set(state.search.listings.map((l) => l.land_type))].sort();
  $("#fType").innerHTML = `<option value="">전체</option>` + types.map((t) => `<option>${esc(t)}</option>`).join("");
  const srcs = [...new Set(state.search.listings.map((l) => l.source))];
  $("#fSource").innerHTML = `<option value="">전체</option>` + srcs.map((s) => `<option value="${esc(s)}">${esc(SOURCE_NAMES[s] || s)}</option>`).join("");
  renderResults();
}

function renderMeta() {
  const m = state.search.meta, c = m.criteria;
  const chips = [
    c.sido + (c.sigungu.length ? " " + c.sigungu.join(", ") : " 전체"),
    c.land_types.length ? c.land_types.join("·") : "전체 유형",
    (c.area_min_m2 || c.area_max_m2) && `면적 ${c.area_min_m2 ? area(c.area_min_m2) : ""} ~ ${c.area_max_m2 ? area(c.area_max_m2) : ""}`,
    (c.price_min || c.price_max) && `금액 ${c.price_min ? won(c.price_min) : ""} ~ ${c.price_max ? won(c.price_max) : ""}`,
  ].filter(Boolean);
  const issue = m.issue ? ` · <a href="https://github.com/${esc(repo())}/issues/${m.issue}" target="_blank" rel="noopener">이슈 #${m.issue}</a>` : "";
  $("#searchMeta").innerHTML = `
    <div><b>${esc(m.title)}</b> <span class="muted">${esc(m.created_at.slice(0, 16).replace("T", " "))}${issue}</span></div>
    <div class="chips">${chips.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>
    <ul class="src-status">
      ${m.sources.map((s) => `<li class="${s.ok ? "" : "bad"}">${esc(SOURCE_NAMES[s.source] || s.source)}: ${s.ok ? "" : "⚠ "}${esc(s.message)}</li>`).join("")}
      <li>${esc(m.market_message)}</li><li>${esc(m.score_message)}</li>
    </ul>
    ${c.memo ? `<div class="muted">메모: ${esc(c.memo)}</div>` : ""}`;
}

function filtered() {
  const src = $("#fSource").value, type = $("#fType").value, price = +$("#fPrice").value || 0;
  const minScore = +$("#fScore").value || 0, text = $("#fText").value.trim(), hideFav = $("#fHideFav").checked;
  const list = state.search.listings.filter((l) =>
    (!src || l.source === src) && (!type || l.land_type === type) &&
    (!price || (l.price_manwon ?? 0) <= price) && (!minScore || (l.score ?? 0) >= minScore) &&
    (!text || (l.title + " " + l.address).includes(text)) && (!hideFav || !state.favorites.items[l.id]));
  const by = $("#fSort").value;
  const key = {
    score: (l) => -(l.score ?? -1), price: (l) => l.price_manwon ?? Infinity, area: (l) => -(l.area_m2 ?? 0),
    ratio: (l) => l.market?.ratio ?? Infinity, deadline: (l) => l.deadline || "9999",
  }[by];
  return list.sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0));
}

function cardHTML(l, favMode = false) {
  const fav = state.favorites.items[l.id];
  const ratio = l.market?.ratio;
  const ratioHTML = ratio ? `<span class="ratio ${ratio < 0.9 ? "low" : ratio > 1.1 ? "high" : ""}">주변 시세의 ${Math.round(ratio * 100)}%</span>
      <span class="muted" title="${esc(l.market.basis)} 실거래 ${l.market.samples}건 중위값">(${esc(l.market.basis)})</span>` : "";
  const detail = l.score_detail && Object.keys(l.score_detail).length
    ? Object.entries(l.score_detail).map(([k, v]) => `${esc(k)} ${v == null ? "20km+" : v + "km"}`).join(" · ") : "";
  const mapQ = encodeURIComponent(l.address || l.title);
  const url = safeUrl(l.url);
  const extra = Object.entries(l.extra || {}).filter(([k, v]) => v && k !== "확인 필요" && String(v).length < 120)
    .map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(" · ");
  return `
  <article class="card" data-id="${esc(l.id)}">
    <div class="head">
      <h3>${esc(l.title)}</h3>
      <span class="badge b-${esc(l.source)}">${esc(SOURCE_NAMES[l.source] || l.source)}</span>
    </div>
    <div class="addr">${esc(l.address)}</div>
    <dl class="facts">
      <dt>유형</dt><dd>${esc(l.land_type)}</dd>
      <dt>${l.source === "naver" ? "매매가" : "최저가"}</dt><dd>${won(l.price_manwon)}</dd>
      ${l.appraisal_manwon ? `<dt>감정가</dt><dd>${won(l.appraisal_manwon)}${l.price_manwon ? ` <span class="muted">(${Math.round((100 * l.price_manwon) / l.appraisal_manwon)}%)</span>` : ""}</dd>` : ""}
      <dt>면적</dt><dd>${area(l.area_m2)}</dd>
      ${l.area_m2 && l.price_manwon ? `<dt>평당</dt><dd>${won(Math.round((l.price_manwon / l.area_m2) * PYEONG))}</dd>` : ""}
      ${ratioHTML ? `<dt>시세</dt><dd>${ratioHTML}</dd>` : ""}
      ${l.deadline ? `<dt>${l.source === "naver" ? "확인일" : "입찰/매각"}</dt><dd>${esc(l.deadline)}</dd>` : ""}
      ${l.failed_bids ? `<dt>유찰</dt><dd>${l.failed_bids}회</dd>` : ""}
    </dl>
    ${l.score != null ? `<div class="score"><span>생활 편의 ${l.score}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, l.score))}%"></i></div></div>
      <div class="score-detail">${detail}</div>` : ""}
    ${l.extra?.["확인 필요"] ? `<div class="note">⚠ ${esc(l.extra["확인 필요"])}</div>` : ""}
    ${extra ? `<div class="score-detail">${extra}</div>` : ""}
    ${favMode ? favEditorHTML(l.id, fav) : ""}
    <div class="actions">
      ${favMode ? "" : `<button class="star ${fav ? "on" : ""}" data-act="fav">${fav ? "★ 관심 등록됨" : "☆ 관심"}</button>`}
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">원문 보기</a>` : ""}
      <a href="https://map.kakao.com/?q=${mapQ}" target="_blank" rel="noopener">카카오맵</a>
      <a href="https://map.naver.com/p/search/${mapQ}" target="_blank" rel="noopener">네이버지도</a>
      <a href="https://www.eum.go.kr/" target="_blank" rel="noopener" title="토지이음에서 주소로 용도지역·규제 확인">토지이음</a>
    </div>
  </article>`;
}

function renderResults() {
  if (!state.search) return;
  const list = filtered();
  $("#resultCount").textContent = `${list.length}건 표시 / 전체 ${state.search.listings.length}건`;
  $("#list").innerHTML = list.length ? list.map((l) => cardHTML(l)).join("") : `<div class="empty">조건에 맞는 물건이 없습니다.</div>`;
  if (state.mode === "map") renderMap(list);
  if (state.mode === "market") renderMarket();
}

function renderMap(list) {
  if (!window.L) { $("#map").innerHTML = `<div class="empty">지도를 불러오지 못했습니다.</div>`; return; }
  if (!state.map) {
    state.map = L.map("map").setView([36.4, 127.8], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap" }).addTo(state.map);
    state.layer = L.layerGroup().addTo(state.map);
  }
  state.layer.clearLayers();
  const pts = list.filter((l) => l.lat != null && l.lng != null);
  pts.forEach((l) => L.marker([l.lat, l.lng]).bindPopup(
    `<b>${esc(l.title)}</b><br>${esc(l.address)}<br>${won(l.price_manwon)} · ${area(l.area_m2)}${l.score != null ? "<br>생활 편의 " + l.score : ""}`).addTo(state.layer));
  setTimeout(() => {
    state.map.invalidateSize();
    if (pts.length) state.map.fitBounds(pts.map((l) => [l.lat, l.lng]), { padding: [30, 30], maxZoom: 13 });
  }, 50);
  if (!pts.length) toast("좌표가 있는 물건이 없습니다 (카카오 키를 설정하면 주소로 좌표를 찾습니다).");
}

function renderMarket() {
  const rows = state.search.market || [];
  $("#market").innerHTML = rows.length ? `
    <p class="muted">국토교통부 실거래가 기준, 시군구·유형별 ㎡당 중위 거래가입니다. (단독주택은 대지면적 기준)</p>
    <table><thead><tr><th>시군구</th><th>유형</th><th>거래 수</th><th>㎡당</th><th>평당</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${esc(r.sigungu)}</td><td>${esc(r.land_type)}</td><td class="num">${r.count}</td>
      <td class="num">${won(Math.round(r.median_per_m2))}</td><td class="num">${won(Math.round(r.median_per_pyeong))}</td></tr>`).join("")}
    </tbody></table>` : `<div class="empty">실거래가 자료가 없습니다.</div>`;
}

function setMode(mode) {
  state.mode = mode;
  $("#showList").classList.toggle("on", mode === "list");
  $("#showMap").classList.toggle("on", mode === "map");
  $("#showMarket").classList.toggle("on", mode === "market");
  $("#map").hidden = mode !== "map";
  $("#market").hidden = mode !== "market";
  $("#list").hidden = mode === "market";
  renderResults();
}

/* ---------- 관심 목록 ---------- */
function favEditorHTML(id, fav) {
  return `<div class="fav-edit">
    <label>상태 <select data-f="status">${STATUSES.map((s) => `<option ${fav.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></label>
    <label>내 평가 <select data-f="rating">${[0, 1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${+fav.rating === n ? "selected" : ""}>${n ? "★".repeat(n) : "없음"}</option>`).join("")}</select></label>
    <label>조사 메모 <textarea data-f="memo" placeholder="현장 확인 내용, 도로·경사·물 사정, 마을 분위기 등">${esc(fav.memo || "")}</textarea></label>
    <div class="muted">등록 ${esc((fav.saved_at || "").slice(0, 10))}${fav.updated_at ? " · 수정 " + esc(fav.updated_at.slice(0, 10)) : ""} · 검색 ${esc(fav.search_id || "")}</div>
    <div class="row"><button data-act="save">저장</button><button class="ghost" data-act="remove">관심 해제</button></div>
  </div>`;
}

function renderFavorites() {
  const filter = $("#favStatusFilter").value;
  const items = Object.entries(state.favorites.items)
    .filter(([, f]) => !filter || f.status === filter)
    .sort(([, a], [, b]) => (b.rating || 0) - (a.rating || 0) || (b.saved_at || "").localeCompare(a.saved_at || ""));
  $("#favList").innerHTML = items.length
    ? items.map(([id, f]) => cardHTML({ ...f.listing, id }, true)).join("")
    : `<div class="empty">아직 관심 물건이 없습니다. 검색 결과에서 ☆ 관심 을 눌러 추가하세요.</div>`;
}

async function toggleFavorite(id) {
  const l = state.search.listings.find((x) => x.id === id);
  const on = !!state.favorites.items[id];
  const ok = await saveFavorites((data) => {
    if (on) delete data.items[id];
    else data.items[id] = { listing: l, status: "검토중", rating: 0, memo: "", saved_at: new Date().toISOString(), search_id: state.search.meta.id };
  }, `${on ? "관심 해제" : "관심 등록"}: ${l.title}`.slice(0, 120));
  if (ok) { toast(on ? "관심 목록에서 뺐습니다." : "관심 목록에 저장했습니다 ★"); renderResults(); }
}

async function saveFavoriteEdit(card) {
  const id = card.dataset.id, vals = {};
  card.querySelectorAll("[data-f]").forEach((el) => (vals[el.dataset.f] = el.value));
  const ok = await saveFavorites((data) => {
    if (!data.items[id]) return;
    Object.assign(data.items[id], { status: vals.status, rating: +vals.rating, memo: vals.memo, updated_at: new Date().toISOString() });
  }, `관심 물건 메모 수정: ${state.favorites.items[id]?.listing?.title || id}`.slice(0, 120));
  if (ok) { toast("저장했습니다."); renderFavorites(); }
}

function exportCsv() {
  const head = ["상태", "평가", "제목", "주소", "유형", "금액(만원)", "면적(㎡)", "면적(평)", "출처", "링크", "메모", "등록일"];
  const rows = Object.values(state.favorites.items).map((f) => {
    const l = f.listing;
    return [f.status, f.rating, l.title, l.address, l.land_type, l.price_manwon, l.area_m2, l.area_pyeong, SOURCE_NAMES[l.source] || l.source, l.url, f.memo, (f.saved_at || "").slice(0, 10)];
  });
  const csv = [head, ...rows].map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = `관심물건_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}

/* ---------- 화면 전환·설정 ---------- */
function showView(v) {
  state.view = v;
  document.querySelectorAll(".view").forEach((s) => (s.hidden = s.id !== `view-${v}`));
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "favorites") renderFavorites();
  if (v === "favorites") history.replaceState(null, "", "#favorites");
  else if (v === "results" && state.search) history.replaceState(null, "", `#search=${encodeURIComponent(state.search.meta.id)}`);
}

async function saveSettings() {
  const r = $("#repoInput").value.trim(), t = $("#tokenInput").value.trim();
  if (r) store("slp.repo", r);
  if (t) store("slp.token", t);
  $("#settingsMsg").textContent = "확인 중…";
  const res = await fetch(`https://api.github.com/repos/${repo()}`, { headers: ghHeaders() });
  if (!res.ok) { $("#settingsMsg").textContent = `연결 실패 (${res.status}). 저장소 이름과 토큰을 확인해 주세요.`; return; }
  const j = await res.json();
  $("#settingsMsg").textContent = j.permissions?.push ? `✅ ${j.full_name}에 저장할 수 있습니다.` : `⚠ ${j.full_name}을 읽을 수는 있지만 쓰기 권한이 없습니다.`;
  $("#tokenInput").value = "";
  updateTokenHint();
  await loadFavorites();
}
function updateTokenHint() {
  $("#tokenInput").placeholder = token() ? "저장된 토큰 있음 (바꾸려면 새로 입력)" : "github_pat_...";
}

function bind() {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#newSearch").href = `https://github.com/${repo()}/issues/new?template=search.yml`;
  $("#searchSelect").addEventListener("change", (e) => loadSearch(e.target.value));
  ["#fSource", "#fType", "#fSort", "#fHideFav"].forEach((s) => $(s).addEventListener("change", renderResults));
  ["#fPrice", "#fScore", "#fText"].forEach((s) => $(s).addEventListener("input", renderResults));
  $("#showList").addEventListener("click", () => setMode("list"));
  $("#showMap").addEventListener("click", () => setMode("map"));
  $("#showMarket").addEventListener("click", () => setMode("market"));
  $("#list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act=fav]");
    if (b) { b.disabled = true; toggleFavorite(b.closest(".card").dataset.id).finally(() => (b.disabled = false)); }
  });
  $("#favList").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const card = b.closest(".card");
    b.disabled = true;
    try {
      if (b.dataset.act === "save") await saveFavoriteEdit(card);
      if (b.dataset.act === "remove" && confirm("관심 목록에서 뺄까요? 메모도 함께 지워집니다.")) {
        const id = card.dataset.id;
        if (await saveFavorites((d) => delete d.items[id], `관심 해제: ${state.favorites.items[id]?.listing?.title || id}`.slice(0, 120))) renderFavorites();
      }
    } finally { b.disabled = false; }
  });
  $("#favStatusFilter").innerHTML += STATUSES.map((s) => `<option>${s}</option>`).join("");
  $("#favStatusFilter").addEventListener("change", renderFavorites);
  $("#exportCsv").addEventListener("click", exportCsv);
  $("#repoInput").value = repo();
  updateTokenHint();
  $("#saveSettings").addEventListener("click", saveSettings);
  $("#clearToken").addEventListener("click", () => { store("slp.token", null); updateTokenHint(); $("#settingsMsg").textContent = "토큰을 지웠습니다."; });
}

(async function init() {
  bind();
  await loadFavorites();
  await loadIndex();
  if (location.hash === "#favorites") showView("favorites");
})();
