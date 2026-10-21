# -*- coding: utf-8 -*-
"""
即時資金流 — 動畫元件（canvas）
仿 Threads @alpha.ddm 影片：中線兩側的彗星光條 + 粒子流、上 8 名流入 / 下 8 名流出、
大時鐘、時間軸。開啟時從開盤回放，播到最新後進入 LIVE，自己每 30 秒抓 GitHub 快照、
平滑滑到新數字（頁面不用整頁重整，動畫不會被打斷）。
"""
import json
from typing import Dict

import streamlit.components.v1 as components

import flow_core as fc

ELECTRONICS = ["半導體", "電子零組件", "電腦週邊", "電腦及週邊", "光電", "通信網路",
               "電子通路", "資訊服務", "其他電子"]

_HTML = r"""
<!doctype html><html><head><meta charset="utf-8">
<style>
:root { --bg:#07090d; --panel:#0f131b; --line:#1c2230; --ink:#e9ecf2; --muted:#7d8597;
        --red:#ff4d5e; --green:#2fd38a; --clock:#d9f24a; }
* { box-sizing:border-box; margin:0; padding:0; }
html,body { background:var(--bg); color:var(--ink);
  font-family:-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif; overflow:hidden; }
.wrap { max-width:760px; margin:0 auto; padding:18px 18px 10px; }
.mono { font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
header { display:flex; justify-content:space-between; align-items:flex-start; }
h1 { font-size:26px; font-weight:700; letter-spacing:1px; }
.sub { color:var(--muted); font-size:13px; margin-top:6px; }
.clock { color:var(--clock); font-size:40px; font-weight:700; line-height:1; text-shadow:0 0 18px rgba(217,242,74,.35); }
.live { display:inline-block; font-size:11px; padding:2px 7px; border-radius:9px; margin-top:6px;
  border:1px solid var(--line); color:var(--muted); float:right; }
.live.on { color:var(--red); border-color:rgba(255,77,94,.5); }
.live.on::before { content:"● "; animation:blink 1.2s infinite; }
@keyframes blink { 50% { opacity:.25 } }
.kpis { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin:16px 0 10px; }
.kpi { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:10px 14px; min-width:0; }
.kpi .l { color:var(--muted); font-size:12px; }
.kpi .v { font-size:26px; font-weight:700; margin-top:4px; white-space:nowrap; }
.kpi .n { font-size:15px; font-weight:700; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kpi .s { font-size:12px; margin-top:2px; }
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; vertical-align:middle; }
.legend { text-align:center; font-size:12px; margin:4px 0 2px; }
.legend span { margin:0 8px; }
canvas { display:block; width:100%; }
.tl { margin-top:6px; }
.track { position:relative; height:16px; cursor:pointer; }
.track .rail { position:absolute; left:0; right:0; top:7px; height:2px; background:var(--line); border-radius:2px; }
.track .fill { position:absolute; left:0; top:7px; height:2px; background:var(--clock); border-radius:2px; }
.track .knob { position:absolute; top:2px; width:12px; height:12px; margin-left:-6px; border-radius:50%;
  background:var(--clock); box-shadow:0 0 10px rgba(217,242,74,.6); }
.tl .ends { display:flex; justify-content:space-between; color:var(--muted); font-size:11px; margin-top:2px; }
.ctrl { display:flex; gap:8px; align-items:center; margin-top:8px; }
.ctrl button { background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px;
  padding:5px 12px; font-size:12px; cursor:pointer; }
.ctrl button.sel { border-color:var(--clock); color:var(--clock); }
.ctrl .sp { flex:1; }
.note { color:var(--muted); font-size:11px; }
@media (max-width:520px) { h1 { font-size:21px; } .clock { font-size:30px; } .kpi .v { font-size:20px; }
  .kpi { padding:8px 10px; } .kpis { gap:6px; } }
</style></head><body><div class="wrap">
<header>
  <div><h1>即時資金流</h1><div class="sub" id="sub"></div></div>
  <div><div class="clock mono" id="clock">--:--</div><div class="live" id="live">回放</div></div>
</header>
<div class="kpis">
  <div class="kpi"><div class="l">全市場 · 開盤到現在</div><div class="v mono" id="kTot">—</div></div>
  <div class="kpi"><div class="l">吸金最多</div><div class="n" id="kTopN">—</div><div class="s mono" id="kTopV"></div></div>
  <div class="kpi"><div class="l">失血最多</div><div class="n" id="kBotN">—</div><div class="s mono" id="kBotV"></div></div>
</div>
<div class="legend"><span style="color:var(--green)">流出</span><span style="color:var(--red)">流入</span></div>
<canvas id="cv"></canvas>
<div class="tl">
  <div class="track" id="track"><div class="rail"></div><div class="fill" id="fill"></div><div class="knob" id="knob"></div></div>
  <div class="ends mono"><span id="t0"></span><span id="t1"></span></div>
</div>
<div class="ctrl">
  <button id="play">❚❚</button>
  <button data-sp="2">2×</button><button data-sp="5" class="sel">5×</button><button data-sp="15">15×</button>
  <span class="sp"></span>
  <span class="note" id="note"></span>
  <button id="goLive">LIVE ▸</button>
</div>
</div>
<script>
const SNAP = __SNAP__, IS_LIVE = __LIVE__, REMOTE = __REMOTE__, ELEC = new Set(__ELEC__);
const RED = "#ff4d5e", GREEN = "#2fd38a", TOPN = 8, ROW_H = 34, GAP_H = 18;
const $ = id => document.getElementById(id);
const toM = s => +s.slice(0, 2) * 60 + +s.slice(3, 5);
const hhmm = m => { m = Math.floor(m); return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); };
const fmt = v => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2) + " 億";
const dotColor = s => ELEC.has(s) ? "#e5f05a" : (s === "金融保險" ? "#4aa8ff" : "#9b7bf0");

// ── 資料：每產業「累積淨額（億）」對齊分鐘 ───────────────────────────────
let D;
function prep(snap) {
  const mins = snap.minutes.map(toM), names = Object.keys(snap.sectors);
  const cum = {};
  for (const s of names) {
    const v = snap.sectors[s]; let c = 0;
    cum[s] = mins.map((_, i) => (c += ((v.in[i] || 0) - (v.out[i] || 0)) / 100));
  }
  return { snap, mins, names, cum };
}
// 時間 t（分鐘）→ 各產業累積值；分鐘之間線性內插，動畫才會連續
function valuesAt(t) {
  const m = D.mins, out = {};
  if (!m.length) return out;
  let k = 0;
  while (k < m.length - 1 && m[k + 1] <= t) k++;
  const f = t <= m[0] ? 0 : (k < m.length - 1 ? Math.min(1, (t - m[k]) / (m[k + 1] - m[k])) : 0);
  for (const s of D.names) {
    const a = D.cum[s][k], b = k < m.length - 1 ? D.cum[s][k + 1] : a;
    out[s] = t < m[0] ? 0 : a + (b - a) * f;
  }
  return out;
}

// ── 狀態 ────────────────────────────────────────────────────────────────
D = prep(SNAP);
const last = () => D.mins[D.mins.length - 1];
let t = D.mins[0], playing = true, speed = 5, mode = "replay";   // replay | live
let liveTarget = last();
const rows = {};          // s → {y, a, v, rate, parts:[]}
let scale = 1, tgt = null, tgtAge = 9, settle = false;

$("sub").textContent = SNAP.date.replace(/-/g, "/") + " " + hhmm(D.mins[0]) + "–" + hhmm(last()) + " · 全天的主動買賣淨額";
$("t0").textContent = hhmm(D.mins[0]);

// ── canvas ──────────────────────────────────────────────────────────────
const cv = $("cv"), ctx = cv.getContext("2d");
let W = 0, H = 0, DPR = 1;
function resize() {
  DPR = window.devicePixelRatio || 1; W = cv.clientWidth;
  H = ROW_H * TOPN * 2 + GAP_H + 8;
  cv.width = W * DPR; cv.height = H * DPR; cv.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener("resize", resize); resize();

function layoutTargets(vals) {
  const ranked = Object.entries(vals).sort((a, b) => b[1] - a[1]);
  const pos = ranked.filter(([, v]) => v > 0.005).slice(0, TOPN);
  const neg = ranked.filter(([, v]) => v < -0.005).slice(-TOPN);
  const tgt = {};
  pos.forEach(([s], i) => tgt[s] = 4 + i * ROW_H);
  neg.forEach(([s], i) => tgt[s] = 4 + TOPN * ROW_H + GAP_H + (TOPN - neg.length + i) * ROW_H);
  return tgt;
}

function draw(dt) {
  const vals = valuesAt(t);
  // 排名每 0.4 秒才重算一次：開盤數字都很小時不會一直洗牌、疊在一起
  tgtAge += dt; if (!tgt || tgtAge > 0.4 || settle) { tgt = layoutTargets(vals); tgtAge = 0; }
  const k = settle ? 1 : null; settle = false;
  const narrow = W < 480;
  const nameX = narrow ? 8 : 14, valX = W - 8;
  const zoneL = narrow ? 92 : 150, zoneR = W - (narrow ? 88 : 118);
  const cx = (zoneL + zoneR) / 2, half = (zoneR - zoneL) / 2;
  // 比例尺：跟著目前最大值慢慢調整，避免跳動
  const mx = Math.max(1, ...Object.values(vals).map(Math.abs));
  scale += (mx - scale) * (k || Math.min(1, dt * 3));

  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(255,255,255,0.06)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(cx + .5, 0); ctx.lineTo(cx + .5, H); ctx.stroke();

  for (const s of D.names) {
    let r = rows[s];
    const inSet = s in tgt;
    if (!r) { if (!inSet) continue; r = rows[s] = { y: tgt[s], a: 0, v: vals[s], prev: vals[s], rate: 0, parts: [] }; }
    if (inSet) r.y += (tgt[s] - r.y) * (k || Math.min(1, dt * 6));
    r.a += ((inSet ? 1 : 0) - r.a) * (k || Math.min(1, dt * 5));
    r.v = vals[s];
    // 流速：每「市場分鐘」的淨流量（億/分），決定粒子密度與速度
    const dm = Math.max(1e-6, r.dtm || 0);
    r.rate += (((r.v - r.prev) / Math.max(dm, 1e-3)) - r.rate) * Math.min(1, dt * 2);
    r.prev = r.v; r.dtm = 0;
    if (r.a < 0.02 && !inSet) { delete rows[s]; continue; }

    const y = r.y + ROW_H / 2, a = r.a, v = r.v, dir = v >= 0 ? 1 : -1;
    const len = Math.min(1, Math.abs(v) / scale) * half, col = v >= 0 ? RED : GREEN;
    const head = cx + dir * len;
    ctx.globalAlpha = a;

    // 第一名：淡色底
    if (tgt[s] === 4 && v > 0) { ctx.fillStyle = "rgba(255,255,255,0.035)"; roundRect(2, r.y + 2, W - 4, ROW_H - 4, 8); ctx.fill(); }

    // 名稱 + 色點
    ctx.fillStyle = dotColor(s); ctx.beginPath(); ctx.arc(nameX + 4, y, 3.2, 0, 7); ctx.fill();
    ctx.fillStyle = "#e9ecf2"; ctx.font = (narrow ? "13px" : "15px") + ' -apple-system,"PingFang TC","Noto Sans TC",sans-serif';
    ctx.textBaseline = "middle"; ctx.textAlign = "left"; ctx.fillText(s, nameX + 14, y + 1);

    // 光條：中線 → 頭，漸層
    if (len > 1) {
      const g = ctx.createLinearGradient(cx, 0, head, 0);
      g.addColorStop(0, hexA(col, 0.0)); g.addColorStop(0.6, hexA(col, 0.35)); g.addColorStop(1, hexA(col, 0.85));
      ctx.fillStyle = g; ctx.fillRect(Math.min(cx, head), y - 2.5, Math.abs(head - cx), 5);
    }
    // 粒子流：往頭的方向跑，流速越快越密
    const speedPx = 60 + Math.min(240, Math.abs(r.rate) / scale * half * 25);
    const spawn = (0.6 + Math.min(14, Math.abs(r.rate) * 6)) * (len / half + 0.15) * (mode === "live" || playing ? 1 : 0.15);
    r.acc = (r.acc || 0) + spawn * dt * 10;
    while (r.acc >= 1 && r.parts.length < 90) { r.acc -= 1; r.parts.push({ p: Math.random() * 0.15, j: (Math.random() - 0.5) * 6, l: 3 + Math.random() * 9 }); }
    if (r.acc >= 1) r.acc = 0;
    ctx.fillStyle = col;
    for (let i = r.parts.length - 1; i >= 0; i--) {
      const q = r.parts[i];
      q.p += (speedPx * dt) / Math.max(30, len);
      if (q.p >= 1) { r.parts.splice(i, 1); continue; }
      const x = cx + dir * q.p * len;
      ctx.globalAlpha = a * (0.25 + 0.6 * q.p);
      ctx.fillRect(dir > 0 ? x - q.l : x, y + q.j - 0.75, q.l, 1.5);
    }
    ctx.globalAlpha = a;
    // 頭：發光圓點，越大筆越大顆
    if (len > 1) {
      const rad = 2.5 + 4.5 * Math.min(1, Math.abs(v) / scale);
      const gl = ctx.createRadialGradient(head, y, 0, head, y, rad * 3.2);
      gl.addColorStop(0, hexA(col, 0.55)); gl.addColorStop(1, hexA(col, 0));
      ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(head, y, rad * 3.2, 0, 7); ctx.fill();
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(head, y, rad, 0, 7); ctx.fill();
    }
    // 數值
    ctx.fillStyle = col; ctx.textAlign = "right";
    ctx.font = (narrow ? "12px" : "14px") + " ui-monospace,'SF Mono',Menlo,monospace";
    ctx.fillText(fmt(v), valX, y + 1);
    ctx.globalAlpha = 1;
  }
  return vals;
}
function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
function hexA(h, a) { const n = parseInt(h.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }

function kpis(vals) {
  const e = Object.entries(vals); if (!e.length) return;
  const tot = e.reduce((s, [, v]) => s + v, 0);
  const top = e.reduce((a, b) => b[1] > a[1] ? b : a), bot = e.reduce((a, b) => b[1] < a[1] ? b : a);
  const k = $("kTot"); k.textContent = (tot >= 0 ? "+" : "−") + Math.abs(tot).toFixed(1) + " 億"; k.style.color = tot >= 0 ? RED : GREEN;
  $("kTopN").innerHTML = `<span class="dot" style="background:${dotColor(top[0])}"></span>${top[0]}`;
  $("kTopV").textContent = fmt(top[1]); $("kTopV").style.color = RED;
  $("kBotN").innerHTML = `<span class="dot" style="background:${dotColor(bot[0])}"></span>${bot[0]}`;
  $("kBotV").textContent = fmt(bot[1]); $("kBotV").style.color = GREEN;
}

function ui() {
  const a = D.mins[0], b = Math.max(last(), a + 1);
  const p = Math.max(0, Math.min(1, (t - a) / (b - a))) * 100;
  $("fill").style.width = p + "%"; $("knob").style.left = p + "%";
  $("t1").textContent = hhmm(b); $("clock").textContent = hhmm(t);
  const lv = $("live");
  lv.className = "live" + (mode === "live" ? " on" : "");
  lv.textContent = mode === "live" ? "LIVE" : (playing ? "回放 " + speed + "×" : "暫停");
  $("play").textContent = playing || mode === "live" ? "❚❚" : "▶";
  $("goLive").style.display = IS_LIVE && mode !== "live" ? "" : "none";
  $("note").textContent = mode === "live" ? "更新 " + (D.snap.updated || "—") : "";
}

// ── 迴圈 ────────────────────────────────────────────────────────────────
let lastTs = performance.now();
function frame(ts) {
  const dt = Math.min(0.1, (ts - lastTs) / 1000); lastTs = ts;
  const t0 = t;
  if (mode === "replay" && playing) {
    t += speed * dt;                                    // speed = 市場分鐘 / 秒
    if (t >= last()) { t = last(); if (IS_LIVE) mode = "live"; else playing = false; }
  } else if (mode === "live") {
    t += (liveTarget - t) * Math.min(1, dt * 0.8);       // 新資料進來 → 慢慢滑過去
  }
  for (const s in rows) rows[s].dtm = (rows[s].dtm || 0) + (t - t0);
  kpis(draw(dt)); ui();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ── 控制 ────────────────────────────────────────────────────────────────
$("play").onclick = () => {
  if (mode === "live") { mode = "replay"; playing = false; }
  else { if (!playing && t >= last()) t = D.mins[0]; playing = !playing; }
};
document.querySelectorAll("[data-sp]").forEach(b => b.onclick = () => {
  speed = +b.dataset.sp; document.querySelectorAll("[data-sp]").forEach(x => x.classList.toggle("sel", x === b));
  if (mode === "live") { mode = "replay"; t = D.mins[0]; } playing = true;
});
$("goLive").onclick = () => { mode = "live"; liveTarget = last(); };
const track = $("track");
function seek(e) {
  const r = track.getBoundingClientRect(), f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  t = D.mins[0] + f * (Math.max(last(), D.mins[0] + 1) - D.mins[0]);
  mode = "replay"; playing = false; settle = true; for (const s in rows) rows[s].prev = valuesAt(t)[s] ?? 0;
}
// 測試用：#t=11:11 直接跳到該時間並暫停
const hm = location.hash.match(/t=(\d\d:\d\d)/);
if (hm) { t = toM(hm[1]); playing = false; settle = true; }
let drag = false;
track.addEventListener("pointerdown", e => { drag = true; track.setPointerCapture(e.pointerId); seek(e); });
track.addEventListener("pointermove", e => drag && seek(e));
track.addEventListener("pointerup", () => drag = false);

// ── LIVE：每 30 秒抓雲端快照 ───────────────────────────────────────────────
if (IS_LIVE && REMOTE) setInterval(async () => {
  try {
    const r = await fetch(REMOTE + "?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) return;
    const s = await r.json();
    if (s.date === D.snap.date && (s.updated || "") > (D.snap.updated || "") && s.minutes && s.minutes.length) {
      D = prep(s); liveTarget = last();
      $("sub").textContent = s.date.replace(/-/g, "/") + " " + hhmm(D.mins[0]) + "–" + hhmm(last()) + " · 全天的主動買賣淨額";
    }
  } catch (e) {}
}, 30000);
</script></body></html>
"""


def render(snap: Dict, live: bool, height: int = 940) -> None:
    lite = {k: snap[k] for k in ("date", "updated", "source", "minutes", "sectors")}
    html = (_HTML.replace("__SNAP__", json.dumps(lite, ensure_ascii=False))
                 .replace("__LIVE__", "true" if live else "false")
                 .replace("__REMOTE__", json.dumps(fc.REMOTE_SNAPSHOT_URL))
                 .replace("__ELEC__", json.dumps(ELECTRONICS, ensure_ascii=False)))
    components.html(html, height=height, scrolling=False)
