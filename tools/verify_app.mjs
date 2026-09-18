// 發布前執行期探針（CDP 即時版）
//
// 為何不用 --virtual-time-budget：App 頁面會令 headless 的虛擬時鐘停擺，
// 探針的 setTimeout 永不觸發，只能拿到解析期佔位內容。改用 DevTools Protocol
// 直接連上頁面，以真實時間等待並求值。
//
// 為何量網絡而唔量 audio.src：App 有兩個播放器 —— 課程原聲用 `audio`，
// 逐字拼接用另一個 `charAudio`。只讀 `audio.src` 會漏掉逐字路由，
// 所以改由 Network 域攔截真實 mp3 請求，並同期望檔名比對。
//
// 用法：node tools/_cdp_probe.mjs [port]
// 前提：另有 HTTP 服務在服務 D:/Code/cantonese-app/app

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = "D:/Code/cantonese-app";
const PORT = process.argv[2] || "8790";
const TARGET = `http://127.0.0.1:${PORT}/index.html`;
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const DBG = 9333;

/* ---------- 啟動 Edge（remote debugging） ---------- */
const profile = path.join(ROOT, "tools", "_edge_cdp");
fs.rmSync(profile, { recursive: true, force: true });

const edge = spawn(EDGE, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
  "--disable-extensions", "--mute-audio", "--autoplay-policy=no-user-gesture-required",
  `--remote-debugging-port=${DBG}`,
  `--user-data-dir=${profile}`,
  "--window-size=430,1200",
  "about:blank",
], { stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function wsUrl() {
  for (let i = 0; i < 80; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${DBG}/json/list`);
      const list = await r.json();
      const pg = list.find(t => t.type === "page");
      if (pg?.webSocketDebuggerUrl) return pg.webSocketDebuggerUrl;
    } catch { /* 尚未就緒 */ }
    await sleep(250);
  }
  throw new Error("DevTools 端點逾時");
}

const hx = ch => "u" + ch.codePointAt(0).toString(16);
const expectCharFile = (ch, jp) => (jp ? `${hx(ch)}_${jp}.mp3` : `${hx(ch)}_*.mp3`);

let ws;
const report = { jsErrors: [], consoleMsgs: [], audioReqs: [], phases: {} };
try {
  ws = new WebSocket(await wsUrl());
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("ws error")); });

  let id = 0;
  const pending = new Map();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    if (m.method === "Runtime.exceptionThrown") {
      report.jsErrors.push(m.params?.exceptionDetails?.exception?.description
        || m.params?.exceptionDetails?.text || "unknown");
    }
    if (m.method === "Runtime.consoleAPICalled" && m.params?.type === "error") {
      report.consoleMsgs.push((m.params.args || []).map(a => a.value ?? a.description).join(" "));
    }
    if (m.method === "Network.requestWillBeSent") {
      const raw = m.params.request.url;
      if (/\.mp3(\?|$)/.test(raw)) {
        report.audioReqs.push(decodeURIComponent(raw.split("/").pop().split("?")[0]));
      }
    }
  };
  const send = (method, params = {}) => new Promise(res => {
    const n = ++id;
    pending.set(n, res);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const evalIn = async (expr, awaitPromise = true) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise, returnByValue: true });
    const ex = r.result?.exceptionDetails;
    if (ex) throw new Error(ex.exception?.description || ex.text);
    return r.result.result.value;
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Page.navigate", { url: TARGET });

  /* ---- 等 App 完成載入、Store 就緒、目錄渲染 ---- */
  let ready = false;
  for (let i = 0; i < 50; i++) {
    await sleep(500);
    const v = await evalIn(
      "(typeof Store!=='undefined' && Store.ready) && document.querySelectorAll('#domList .dom-head').length>0",
      false);
    if (v === true) { ready = true; break; }
  }
  report.ready = ready;

  /* ---- 靜態 / DOM 檢查 ---- */
  report.phases.static = await evalIn(`(function(){
    const o = {};
    o.store = typeof Store;
    o.storeReady = Store.ready;
    o.storeNative = !!Store.native;
    o.domains = document.querySelectorAll('#domList .dom-head').length;
    o.lessons = document.querySelectorAll('#domList .les').length;
    o.domainNames = [...document.querySelectorAll('#domList .dom-head h3')].map(h => h.textContent.trim());
    o.domainCounts = [...document.querySelectorAll('#domList .dom-head .cnt')].map(c => c.textContent.trim());
    o.manifest = (document.querySelector('link[rel=manifest]')||{}).href||null;
    o.themeColor = (document.querySelector('meta[name=theme-color]')||{}).content||null;
    o.viewportFit = /viewport-fit=cover/.test((document.querySelector('meta[name=viewport]')||{}).content||'');
    o.privacyLink = !!document.querySelector('a[href="privacy.html"]');
    o.meCards = document.querySelectorAll('.me-card').length;
    const b = document.body.innerHTML;
    o.hasAiNote = b.indexOf('AI 合成語音') !== -1;
    o.hasPrivacyCard = b.indexOf('不收集任何個人資料') !== -1;
    o.text2clip = Object.keys(TEXT2CLIP).length;
    o.vocabClip = Object.keys(VOCAB_CLIP).length;
    o.charAudioKeys = Object.keys(CHAR_AUDIO).length;
    o.t2c1 = clipForText('塔吊吊料要有人看。');
    o.t2c2 = clipForText('唔該');
    o.t2c3 = clipForText('你今日有咩事呀？');
    o.t2cMiss = clipForText('呢句一定唔會存在嘅句子XYZ');
    o.charFile_paang4 = charFile('棚','paang4');
    o.charFile_hang4 = charFile('行','haang4');
    o.charFile_hong4 = charFile('行','hong4');
    o.charFile_none = charFile('鑫','zuk6');
    o.swSupported = ('serviceWorker' in navigator);
    return o;
  })()`);

  /* ---- 圖示載入 ---- */
  report.phases.icons = await evalIn(`(async function(){
    const ok = s => new Promise(r => { const i = new Image(); i.onload = () => r(i.naturalWidth); i.onerror = () => r(0); i.src = s; });
    const o = {};
    for (const s of ['icons/icon-192.png','icons/icon-512.png','icons/icon-180.png','icons/icon-maskable-512.png']) o[s] = await ok(s);
    return o;
  })()`);

  /* ---- 首課開啟 + 逐字拼音對齊 ---- */
  report.phases.lesson = await evalIn(`(async function(){
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const o = {};
    document.querySelector('#domList .les').click();
    await sleep(800);
    o.title = document.getElementById('lvTitle').textContent;
    o.sub = document.getElementById('lvSub').textContent;
    const line = document.querySelector('#lvBody .ln-yue');
    const py = document.querySelector('#lvBody .ln-py');
    o.firstLine = line.textContent;
    o.firstPy = py.textContent.trim();
    o.charSpans = document.querySelectorAll('#lvBody .ln-yue .ch').length;
    o.aligned = [...line.querySelectorAll('.ch')].every(c => !!c.dataset.jp);
    // 整句音檔路由
    o.lineClipAttr = document.querySelector('#lvBody .ln').dataset.clip;
    return o;
  })()`);

  /* ---- 逐字路由抽樣（網絡層觀測，逐個字快照） ---- */
  await evalIn(`(function(){ if(typeof closeLesson==='function') closeLesson(); openLesson('con-11'); return 1; })()`, false);
  await sleep(900);

  const sample = await evalIn(`(function(){
    const spans = [...document.querySelectorAll('#lvBody .ln-yue .ch')].slice(0, 8);
    return { title: document.getElementById('lvTitle').textContent, items: spans.map(s => ({ ch: s.dataset.ch, jp: s.dataset.jp || null })) };
  })()`, false);

  const seen = report.audioReqs;
  for (let i = 0; i < sample.items.length; i++) {
    const mark = seen.length;
    await evalIn(`(function(){ document.querySelectorAll('#lvBody .ln-yue .ch')[${i}].click(); return 1; })()`, false);
    await sleep(750);
    const it = sample.items[i];
    const got = seen.slice(mark);
    report.phases["char" + i] = { ch: it.ch, jp: it.jp, expected: expectCharFile(it.ch, it.jp), got, match: got.includes(expectCharFile(it.ch, it.jp)) };
  }
  report.phases.charSampleTitle = sample.title;

  /* ---- 偏好開關（走 Store 適配層） ---- */
  report.phases.prefs = await evalIn(`(function(){
    const o = {};
    o.pyBefore = showPy; togglePy(); o.pyAfter = showPy; togglePy(); o.pyRestored = showPy;
    o.slowBefore = slowMode; toggleSlow(); o.slowAfter = slowMode; toggleSlow(); o.slowRestored = slowMode;
    o.lsKeys = Object.keys(localStorage).sort();
    o.readBack = Store.getItem('yf.py');
    return o;
  })()`, false);

  /* ---- 我的頁：發音引擎卡 ---- */
  report.phases.me = await evalIn(`(async function(){
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    switchTab('me'); await sleep(600);
    const o = {};
    o.cards = document.querySelectorAll('.me-card').length;
    o.engDot = (document.getElementById('engDot')||{}).className || null;
    o.engChars = (document.getElementById('engChars')||{}).textContent || null;
    o.engFiles = (document.getElementById('engFiles')||{}).textContent || null;
    o.engTTS = (document.getElementById('engTTS')||{}).textContent || null;
    o.verLine = (document.getElementById('verLine')||{}).textContent || null;
    o.privacyHref = (document.querySelector('a[href="privacy.html"]')||{}).textContent || null;
    o.hasRecheck = !!document.getElementById('btnRecheck');
    o.hasTtsFirst = !!document.getElementById('btnTTSFirst');
    switchTab('home');
    return o;
  })()`);
} finally {
  try { ws?.close(); } catch { }
  edge.kill();
  fs.rmSync(profile, { recursive: true, force: true });
  // 收集本次運行觸發的音檔請求（去重後按首次出現排序）
  const uniq = [];
  for (const f of report.audioReqs) if (!uniq.includes(f)) uniq.push(f);
  report.audioReqs = uniq;
  console.log(JSON.stringify(report, null, 1));
}
