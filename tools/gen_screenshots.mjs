// 商店截圖生成器（Google Play / App Store 用）
//
// 用 CDP 的裝置模擬把視窗設成手機尺寸再截圖，得到真正的 App 界面（非縮放網頁）。
// 尺寸取 360×640 CSS @3x = 1080×1920，剛好 9:16，符合兩大商店的規格。
//
// 用法：node tools/gen_screenshots.mjs [port]
// 前提：另有 HTTP 服務在服務 D:/Code/cantonese-app/app

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = "D:/Code/cantonese-app";
const OUT = path.join(ROOT, "store", "screenshots");
const PORT = process.argv[2] || "8790";
const TARGET = `http://127.0.0.1:${PORT}/index.html`;
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const DBG = 9334;

const W = 360, H = 640, DPR = 3;   // → 1080 × 1920

fs.mkdirSync(OUT, { recursive: true });
const profile = path.join(ROOT, "tools", "_edge_shot");
fs.rmSync(profile, { recursive: true, force: true });

const edge = spawn(EDGE, [
  "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
  "--disable-extensions", "--mute-audio", "--hide-scrollbars",
  "--force-device-scale-factor=" + DPR,
  `--remote-debugging-port=${DBG}`,
  `--user-data-dir=${profile}`,
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

/* 商店展示需要「已在使用」的狀態：先預置進度，否則首頁顯示 0% 很寒酸。
   注意 store 的 getter 每次都讀 localStorage，所以寫完重繪即生效。 */
const SEED = `
  const d = new Date().toDateString();
  localStorage.setItem('yf.today', JSON.stringify({d: d, n: 4}));
  localStorage.setItem('yf.done', JSON.stringify(['basic-01','basic-02','life-01','life-02','life-03','life-04']));
  localStorage.setItem('yf.stars', JSON.stringify({match: 9, listen: 7}));
  localStorage.setItem('yf.words', JSON.stringify(VOCAB.slice(0,6).map(w => w.y)));
  const pl = [];
  ['basic-01','basic-02','life-01','life-02','life-03'].forEach(id => { for (let i=1;i<=6;i++) pl.push(id+'-c'+i); });
  localStorage.setItem('yf.played', JSON.stringify(pl));
  localStorage.setItem('yf.last', 'life-06');
  return 1;
`;

/* 每個鏡頭：先跑一段頁面內腳本擺好狀態，再截圖 */
const SHOTS = [
  {
    file: "01-home.png",
    note: "首頁 · 學習進度與繼續學習",
    js: `switchTab('home');
         renderRing(); renderResume(); renderHomeWords(); paintStars();
         document.getElementById('sc-home').scrollTop = 0; return 1;`,
  },
  {
    file: "02-lessons.png",
    note: "課程目錄 · 六大板塊",
    js: `switchTab('lessons');
         document.getElementById('sc-lessons').scrollTop = 0; return 1;`,
  },
  {
    file: "03-domain-construction.png",
    note: "課程目錄 · 香港建築業 18 課",
    js: `switchTab('lessons');
         const wrap = document.getElementById('sc-lessons');
         const hs=[...document.querySelectorAll('#domList .dom-head h3')];
         const t=hs.find(h=>h.textContent.includes('建築業'));
         if(t){ wrap.scrollTop = t.closest('.dom-head').offsetTop - 8; }
         return 1;`,
  },
  {
    file: "04-lesson-medical.png",
    note: "課程詳情 · 醫療課核心句（漢字＋粵拼＋對譯）",
    js: `closeLesson(); openLesson('med-03');
         document.getElementById('lvBody').scrollTop = 0; return 1;`,
    wait: 900,
  },
  {
    file: "05-lesson-vocab.png",
    note: "課程詳情 · 詞彙與學習貼士",
    js: `const b=document.getElementById('lvBody');
         const vg=b.querySelector('.vgrid');
         if(vg) b.scrollTop = vg.closest('.blk').offsetTop - 10;
         return 1;`,
    wait: 700,
  },
  {
    file: "06-tapping.png",
    note: "點句發音 · 迷你播放器與粵拼",
    js: `const b=document.getElementById('lvBody'); b.scrollTop = 0;
         const ln=document.querySelector('#lvBody .ln');
         if(ln) ln.click();
         return 1;`,
    wait: 1100,
  },
  {
    file: "07-game.png",
    note: "學習小遊戲 · 配對樂園進行中",
    js: `document.getElementById('miClose').click();
         goGame('match'); return 1;`,
    wait: 1100,
  },
  {
    file: "08-me.png",
    note: "我的 · 發音引擎與本地字庫",
    js: `document.getElementById('miClose').click();
         switchTab('me'); renderMe();
         document.getElementById('sc-me').scrollTop = 0; return 1;`,
    wait: 700,
  },
];

let ws;
try {
  ws = new WebSocket(await wsUrl());
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("ws error")); });

  let id = 0;
  const pending = new Map();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  };
  const send = (method, params = {}) => new Promise(res => {
    const n = ++id;
    pending.set(n, res);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const evalIn = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    const ex = r.result?.exceptionDetails;
    if (ex) throw new Error(ex.exception?.description || ex.text);
    return r.result.result.value;
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: W, height: H, deviceScaleFactor: DPR, mobile: true,
  });
  await send("Page.navigate", { url: TARGET });

  for (let i = 0; i < 50; i++) {
    await sleep(500);
    const v = await evalIn(
      "(typeof Store!=='undefined' && Store.ready) && document.querySelectorAll('#domList .dom-head').length>0");
    if (v === true) break;
  }
  await sleep(600);
  await evalIn(`(function(){ ${SEED} })()`);
  await sleep(400);
  console.log(`App 就緒，開始截圖 ${W}x${H} @${DPR}x → ${W * DPR}x${H * DPR}`);

  for (const s of SHOTS) {
    await evalIn(`(function(){ ${s.js} })()`);
    await sleep(s.wait || 600);
    // 無頭環境禁自動播放，會彈「音頻播放失敗」提示；截圖前一律收掉
    await evalIn(`(function(){ const t=document.getElementById('toast'); if(t) t.classList.remove('show'); return 1; })()`);
    await sleep(200);
    const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const buf = Buffer.from(r.result.data, "base64");
    fs.writeFileSync(path.join(OUT, s.file), buf);
    console.log(`  ${s.file}  ${(buf.length / 1024).toFixed(1)} KB  ${s.note}`);
  }
} finally {
  try { ws?.close(); } catch { }
  edge.kill();
  fs.rmSync(profile, { recursive: true, force: true });
}
