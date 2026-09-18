// 在模擬器/真機上依序驅動 App 並截圖（CDP 驅動 + adb screencap）
//
// 用法：node tools/emu_shots.mjs [port] [outDir]
// 前提：adb forward tcp:9222 localabstract:webview_devtools_remote_<pid> 已建立
//
// 為何不用 adb shell input tap：座標要自己算，而且會受螢幕縮放影響。
// 用 CDP 直接呼叫 App 內部函式切換場景最穩定，截圖則交給 adb（拿的是真實 framebuffer）。

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ADB = "C:/Users/Luffy/AppData/Local/Android/Sdk/platform-tools/adb.exe";
const PORT = process.argv[2] || "9222";
const OUT = process.argv[3] || "D:/Code/cantonese-app/store/screenshots-emu";
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
const tgt = list.find(t => t.type === "page");

// WebView 在螢幕上的實際位置。若 screenY > 0，代表 WebView 已經被系統內縮到安全區內，
// 此時 env(safe-area-inset-*) 本來就應該係 0，唔算問題。
// （之前誤報就係因為假設咗 App 一定係 edge-to-edge。）
let screenY = 0, screenX = 0, cardW = 0, cardH = 0;
try {
  const d = JSON.parse(tgt.description);
  screenY = d.screenY ?? 0; screenX = d.screenX ?? 0;
  cardW = d.width ?? 0; cardH = d.height ?? 0;
} catch { /* 舊版 WebView 冇 description */ }
const ws = new WebSocket(tgt.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("ws")); });

let id = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(res => { const n = ++id; pending.set(n, res); ws.send(JSON.stringify({ id: n, method, params })); });
const evalIn = async (expr, awaitPromise = true) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise, returnByValue: true, userGesture: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
  return r.result.result.value;
};

await send("Runtime.enable");

// 場景：[檔名, 要執行的 JS, 額外等待毫秒]
const scenes = [
  ["emu-01-home",       `(function(){ document.getElementById('toast').classList.remove('show'); switchTab('home'); return 1; })()`, 900],
  ["emu-02-lessons",    `(function(){ switchTab('lessons'); return 1; })()`, 900],
  ["emu-03-lesson-top", `(function(){ openLesson('con-11'); return 1; })()`, 1000],
  // .screen 是同一批 DOM 節點，switchTab 不會重設 scrollTop，
  // 所以要明確歸零，否則上一輪留下的捲動位置會污染這次截圖
  ["emu-04-me",         `(function(){ switchTab('me');
      const s=document.querySelector('#sc-me'); if(s) s.scrollTop=0; return 1; })()`, 900],
  ["emu-05-games",      `(function(){ switchTab('games'); return 1; })()`, 900],
  // 滾到「我的」的發音引擎卡，驗證系統音色狀態文案
  ["emu-06-me-engine",  `(function(){ switchTab('me');
      const s=document.querySelector('#sc-me');
      const card=[...document.querySelectorAll('#sc-me *')].find(e=>e.children.length===0 && /發音引擎/.test(e.textContent));
      if (card) { const top=card.getBoundingClientRect().top + (s?s.scrollTop:0);
                  s.scrollTop = Math.max(0, top - 60); }
      else if (s) s.scrollTop = s.scrollHeight - 700;
      return 1; })()`, 1500],
];

// 由 dumpsys 讀到：狀態列 136px、導覽列 63px（1080x2400 @ density 420）
const STATUS_BAR_CSS = 136 / 2.625;
const NAV_BAR_CSS = 63 / 2.625;
const EDGE_TO_EDGE = screenY === 0;

console.log(`WebView 位置：screenX=${screenX} screenY=${screenY} 尺寸=${cardW}x${cardH}`);
console.log(`狀態列 ${STATUS_BAR_CSS.toFixed(1)} CSS px / 導覽列 ${NAV_BAR_CSS.toFixed(1)} CSS px`);
console.log(EDGE_TO_EDGE
  ? "模式：edge-to-edge（WebView 佔滿全屏）→ 依賴 env(safe-area-inset-*) 讓開系統列\n"
  : "模式：WebView 已被系統內縮在安全區內 → env() 回 0 屬正常，毋須補償\n");

for (const [name, js, wait] of scenes) {
  await evalIn(js, false);
  await sleep(wait);
  // 移除可能遮擋的 toast
  await evalIn(`(function(){ const t=document.getElementById('toast'); if(t) t.classList.remove('show'); return 1; })()`, false);
  await sleep(150);
  const geo = await evalIn(`(function(){
    const sc = document.querySelector('.screen.active');
    const lv = document.querySelector('.lv.show');
    const root = lv || sc;
    if (!root) return null;
    let minTop = Infinity, items = [];
    root.querySelectorAll('*').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.opacity === '0') return;
      if (r.top < minTop) minTop = r.top;
      if (r.top >= 0 && r.top < 60 && items.length < 6) items.push(String(el.className) + '@' + Math.round(r.top));
    });
    const tb = document.querySelector('.tabbar');
    const probe = css => { const d=document.createElement('div');
      d.style.cssText='position:fixed;top:0;left:0;width:0;height:'+css;
      document.body.appendChild(d); const h=d.getBoundingClientRect().height; d.remove(); return h; };
    return { topMostVisibleCssY: Math.round(minTop), nearTop: items,
             envTop: probe('env(safe-area-inset-top)'),
             envBottom: probe('env(safe-area-inset-bottom)'),
             tabbarBottom: tb ? Math.round(tb.getBoundingClientRect().bottom) : null,
             viewportH: innerHeight };
  })()`, false);
  const shot = spawnSync(ADB, ["exec-out", "screencap", "-p"], { maxBuffer: 64 * 1024 * 1024 });
  const f = path.join(OUT, name + ".png");
  fs.writeFileSync(f, shot.stdout);

  // 只有 edge-to-edge 模式下，內容才會真的撞到系統列
  const need = EDGE_TO_EDGE ? STATUS_BAR_CSS : 0;
  const bad = geo && need > 0 && geo.topMostVisibleCssY < need - 1;
  console.log(`${name.padEnd(20)} 最頂內容 y=${String(geo && geo.topMostVisibleCssY).padStart(4)}  `
    + `envTop=${geo ? geo.envTop : "?"}  envBottom=${geo ? geo.envBottom : "?"}  `
    + (EDGE_TO_EDGE ? (bad ? "⚠ 撞到狀態列" : "✓") : "✓（WebView 已內縮）"));
  if (geo && geo.nearTop.length) console.log("   近頂元素:", geo.nearTop.join("  "));
  console.log(`   → ${path.basename(f)}  ${(shot.stdout.length / 1024).toFixed(0)} KB`);
}

ws.close();
