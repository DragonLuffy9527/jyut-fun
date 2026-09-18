// 真機 Android WebView 探針（CDP over adb forward）
//
// 與 tools/verify_app.mjs 的分工：
//   verify_app.mjs   → 桌面 Edge，快，用來跑日常靜態/邏輯回歸
//   probe_webview.mjs → 模擬器/真機的 Chromium WebView，驗證「只在 Android 才會踩到」的問題
//                       （Capacitor 原生儲存、file/https 來源、媒體自動播放策略、安全區）
//
// 用法：
//   adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>
//   node tools/probe_webview.mjs [port]
//
// 為何用 Input.dispatchMouseEvent 而非 element.click()：
//   腳本呼叫的 click() 不是 trusted user gesture，Chromium 會擋掉音訊播放，
//   於是逐字路由量不到真實行為。改發真實指標事件就等同真人點擊。

const PORT = process.argv[2] || "9222";

/* ---------- 找頁面 target ---------- */
async function pageTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const pg = list.find(t => t.type === "page" && /localhost|index\.html|capacitor/.test(t.url))
        || list.find(t => t.type === "page");
      if (pg?.webSocketDebuggerUrl) return pg;
    } catch { /* 尚未就緒 */ }
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error("找不到 WebView target（adb forward 是否已建立？）");
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const hx = ch => "u" + ch.codePointAt(0).toString(16);
const expectCharFile = (ch, jp) => (jp ? `${hx(ch)}_${jp}.mp3` : `${hx(ch)}_*.mp3`);

const tgt = await pageTarget();
const report = {
  target: { url: tgt.url, title: tgt.title, type: tgt.type },
  jsErrors: [], consoleErrors: [], mp3: [], phases: {},
};

const ws = new WebSocket(tgt.webSocketDebuggerUrl);
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
    report.consoleErrors.push((m.params.args || []).map(a => a.value ?? a.description).join(" "));
  }
  if (m.method === "Network.requestWillBeSent") {
    const raw = m.params.request.url;
    if (/\.mp3(\?|$)/.test(raw)) report.mp3.push(decodeURIComponent(raw.split("/").pop().split("?")[0]));
  }
};
const send = (method, params = {}) => new Promise(res => {
  const n = ++id; pending.set(n, res);
  ws.send(JSON.stringify({ id: n, method, params }));
});
const evalIn = async (expr, awaitPromise = true) => {
  const r = await send("Runtime.evaluate", {
    expression: expr, awaitPromise, returnByValue: true, userGesture: true,
  });
  const ex = r.result?.exceptionDetails;
  if (ex) throw new Error(ex.exception?.description || ex.text);
  return r.result.result.value;
};
// 真實指標點擊（產生 trusted user gesture）
async function realClickAt(x, y) {
  const base = { x: Math.round(x), y: Math.round(y), button: "left", clickCount: 1 };
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", ...base, button: "none" });
  await send("Input.dispatchMouseEvent", { type: "mousePressed", ...base });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", ...base });
}
async function realClick(sel, idx = 0) {
  const b = await evalIn(`(function(){const e=document.querySelectorAll(${JSON.stringify(sel)})[${idx}];
    if(!e) return null;
    e.scrollIntoView({block:'center'});
    const r2=e.getBoundingClientRect();
    const x=r2.x+r2.width/2, y=r2.y+r2.height/2;
    const at=document.elementFromPoint(x,y);
    return {x:x, y:y, w:r2.width, h:r2.height,
            hitTag: at?at.tagName:null, hitCls: at?String(at.className):null, hitIsTarget: at===e};})()`, false);
  if (!b) throw new Error("元素不存在：" + sel + "[" + idx + "]");
  // 守衛：rect 為 0 代表元素在 display:none 的子樹裡 —— 直接拋錯，
  // 否則會靜默地在 (0,0) 空點一下，讓整段驗證變成假通過。
  if (b.w === 0 && b.h === 0) throw new Error("元素不可見（rect 為 0，祖先可能 display:none）：" + sel + "[" + idx + "]");
  await realClickAt(b.x, b.y);
  return b;
}

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");

  /* ---- 重新載入，取得乾淨起點 ---- */
  await send("Page.reload", { ignoreCache: false });
  let ready = false;
  for (let i = 0; i < 60; i++) {
    await sleep(400);
    try {
      const v = await evalIn(
        "(typeof Store!=='undefined' && Store.ready) && document.querySelectorAll('#domList .dom-head').length>0",
        false);
      if (v === true) { ready = true; break; }
    } catch { /* 載入中 */ }
  }
  report.phases.load = { ready, waitedMs: null };

  /* ---- 1. 環境 / 原生能力（只有 Android 才有） ---- */
  report.phases.env = await evalIn(`(function(){
    const o = {};
    o.href = location.href;
    o.origin = location.origin;
    o.protocol = location.protocol;
    o.hasCapacitor = typeof window.Capacitor !== 'undefined';
    if (o.hasCapacitor && window.Capacitor.getPlatform) o.capacitorPlatform = window.Capacitor.getPlatform();
    o.storeReady = Store.ready;
    o.storeNative = !!Store.native;
    o.hasPreferencesPlugin = !!(window.Capacitor && Capacitor.Plugins && Capacitor.Plugins.Preferences);
    o.swRegistered = !!navigator.serviceWorker.controller;
    o.devicePixelRatio = window.devicePixelRatio;
    o.viewport = [innerWidth, innerHeight];

    // 實測 env(safe-area-inset-*)：Capacitor 注入的自訂屬性會失敗（SystemBars.java 有 bug），
    // 但 app 用的是原生 env()，所以要直接量 env() 解出來的值。
    const probe = css => { const d=document.createElement('div');
      d.style.cssText='position:fixed;top:0;left:0;width:0;height:'+css;
      document.body.appendChild(d); const h=d.getBoundingClientRect().height; d.remove(); return h; };
    o.inset = {
      top: probe('env(safe-area-inset-top)'),
      bottom: probe('env(safe-area-inset-bottom)'),
      left: probe('env(safe-area-inset-left)'),
      right: probe('env(safe-area-inset-right)'),
    };
    o.injectedVar = {
      top: getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-top').trim(),
      bottom: getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-bottom').trim(),
    };
    // 實際元素有沒有被系統列蓋住
    const sc = document.querySelector('.screen.active') || document.querySelector('.screen');
    const tb = document.querySelector('.tabbar');
    o.layout = {
      screenPaddingTop: sc ? getComputedStyle(sc).paddingTop : null,
      screenPaddingBottom: sc ? getComputedStyle(sc).paddingBottom : null,
      tabbarBottom: tb ? Math.round(tb.getBoundingClientRect().bottom) : null,
      tabbarPaddingBottom: tb ? getComputedStyle(tb).paddingBottom : null,
      viewportH: innerHeight,
      tabbarFullyVisible: tb ? tb.getBoundingClientRect().bottom <= innerHeight + 0.5 : null,
    };
    return o;
  })()`, false);

  /* ---- 2. 內容完整性 ---- */
  report.phases.content = await evalIn(`(function(){
    const o = {};
    o.domains = document.querySelectorAll('#domList .dom-head').length;
    o.lessons = document.querySelectorAll('#domList .les').length;
    o.domainNames = [...document.querySelectorAll('#domList .dom-head h3')].map(h=>h.textContent.trim());
    o.domainCounts = [...document.querySelectorAll('#domList .dom-head .cnt')].map(c=>c.textContent.trim());
    o.meChars = (document.getElementById('engChars')||{}).textContent || null;
    o.meFiles = (document.getElementById('engFiles')||{}).textContent || null;
    o.hasPrivacyLink = !!document.querySelector('a[href="privacy.html"]');
    return o;
  })()`, false);

  /* ---- 3. 目錄列表（點課程 tab，確認渲染；務必 awaitPromise=true，
         否則 switchTab 的後續步驟會在後面偷偷執行 closeLesson 把課程層關掉） ---- */
  report.phases.catalog = await evalIn(`(async function(){
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    const o={};
    if (typeof switchTab==='function') { switchTab('lessons'); await sleep(500); }
    o.domHeads = document.querySelectorAll('#domList .dom-head').length;
    o.lessons = document.querySelectorAll('#domList .les').length;
    if (typeof switchTab==='function') { switchTab('home'); await sleep(400); }
    o.lessonViewClosed = !document.querySelector('.lv.show');
    return o;
  })()`);

  /* ---- 4. 開一課（建築業），驗證逐字拼音對齊 ---- */
  await evalIn(`(function(){ if(typeof openLesson==='function') openLesson('con-11'); return 1; })()`, false);
  await sleep(900);
  const sample = await evalIn(`(function(){
    const spans=[...document.querySelectorAll('#lvBody .ln-yue .ch')].slice(0,6);
    return { overlayVisible: !!document.querySelector('.lv.show'),
             title:(document.getElementById('lvTitle')||{}).textContent||null,
             line: (document.querySelector('#lvBody .ln-yue')||{}).textContent||null,
             py: (document.querySelector('#lvBody .ln-py')||{}).textContent||null,
             chars: spans.map(s=>({ch:s.dataset.ch, jp:s.dataset.jp||null})) };
  })()`, false);
  report.phases.lesson = {
    overlayVisible: sample.overlayVisible,
    title: sample.title, line: sample.line, py: (sample.py || "").trim(),
    charSpans: sample.chars.length,
    allAligned: sample.chars.every(c => !!c.jp),
  };
  if (!sample.overlayVisible) {
    throw new Error("課程覆蓋層未顯示（.lv 缺 .show），後續點讀驗證會失效");
  }

  /* ---- 5. 逐字路由（真實觸摸 → 讀兩個播放器的解析結果） ----
     為何不再只量 Network 域：Capacitor 用 WebViewLocalServer 在 shouldInterceptRequest
     攔截 https://localhost/* 的本地資源，這些請求不會出現在 DevTools 的 Network 域，
     所以 mp3 請求數永遠是 0。改為直接讀播放器狀態 —— 邊個播放器拿到 src 就是走咗邊條路。 */
  const playerState = () => evalIn(`(function(){
    const b = u => (u && !/^(about:blank|)$/.test(u)) ? decodeURIComponent(u.split('/').pop().split('?')[0]) : null;
    const o = {};
    // 診斷：確認 eval 真的落在 App 的 JS 全域（top-level const 在 classic script 中
    // 屬於 global lexical scope，typeof 不會拋錯，只會回 'undefined'）
    o.probe = { charType: typeof charAudio, lineType: typeof audio,
                charRawSrc: (typeof charAudio === 'object' && charAudio) ? charAudio.src : null,
                lineRawSrc: (typeof audio === 'object' && audio) ? audio.src : null };
    try { o.curClip = (typeof curClip!=='undefined') ? curClip : null; } catch(e) { o.curClip='n/a'; }
    try { o.char = { file:b(charAudio.src), readyState:charAudio.readyState, paused:charAudio.paused,
                     time:+charAudio.currentTime.toFixed(2), dur:isFinite(charAudio.duration)?+charAudio.duration.toFixed(2):null,
                     err:charAudio.error?charAudio.error.code:null }; } catch(e) { o.char = 'n/a:' + e.message; }
    try { o.line = { file:b(audio.src), readyState:audio.readyState, paused:audio.paused,
                     time:+audio.currentTime.toFixed(2), dur:isFinite(audio.duration)?+audio.duration.toFixed(2):null,
                     err:audio.error?audio.error.code:null }; } catch(e) { o.line = 'n/a:' + e.message; }
    return o;
  })()`, false);
  const pick = st => {
    const c = st.char && st.char !== 'n/a' && st.char.file ? st.char : null;
    const l = st.line && st.line !== 'n/a' && st.line.file ? st.line : null;
    return l ? { route: 'course-clip', player: 'audio', ...l }
             : (c ? { route: 'char-clip', player: 'charAudio', ...c } : { route: 'none' });
  };

  const seen = report.mp3;
  for (let i = 0; i < sample.chars.length; i++) {
    const mark = seen.length;
    let hit = null;
    try { hit = await realClick("#lvBody .ln-yue .ch", i); } catch (e) { report.phases["char" + i] = { error: String(e) }; continue; }
    await sleep(320);
    const rawMid = await playerState();
    const mid = pick(rawMid);
    await sleep(700);
    const end = pick(await playerState());
    const it = sample.chars[i];
    report.phases["char" + i] = {
      ch: it.ch, jp: it.jp,
      expectedCharFile: expectCharFile(it.ch, it.jp),
      hit, rawMid, at320ms: mid, at1020ms: end,
      loaded: (mid.readyState >= 2) || (end.readyState >= 2),
      advanced: (end.time > 0) || (mid.time > 0),
      networkMp3: seen.slice(mark),
    };
  }

  /* ---- 6. 整句課程原聲（應落到 audio 播放器，並出現在迷你播放器） ---- */
  {
    const mark = seen.length;
    try { await realClick("#lvBody .ln", 0); } catch { }
    await sleep(900);
    report.phases.lineClip = {
      ...pick(await playerState()),
      miniVisible: await evalIn(`!!document.querySelector('#mini.show')`, false),
      miniTitle: await evalIn(`(document.getElementById('miTitle')||{}).textContent||null`, false),
      networkMp3: seen.slice(mark),
    };
  }

  /* ---- 7. Store 讀寫往返（Android 上要落到原生 Preferences） ---- */
  report.phases.store = await evalIn(`(async function(){
    const k='yf.__probe', v='ok-' + Date.now();
    const before = Store.getItem(k);
    Store.setItem(k, v);
    const after = Store.getItem(k);
    const inLs = localStorage.getItem(k);
    await new Promise(r=>setTimeout(r,600));       // 等鏡像寫入原生
    Store.removeItem(k);
    return { before, after, wroteValue:v, roundTrip: after===v, mirroredToLocalStorage: inLs===v };
  })()`);

  /* ---- 8. 偏好開關 + 我的頁 ---- */
  report.phases.me = await evalIn(`(async function(){
    const sleep=ms=>new Promise(r=>setTimeout(r,ms));
    const o={};
    o.pyBefore=showPy; togglePy(); o.pyAfter=showPy; togglePy(); o.pyRestored=showPy;
    if (typeof switchTab==='function') { switchTab('me'); await sleep(700); }
    o.cards=document.querySelectorAll('.me-card').length;
    o.engChars=(document.getElementById('engChars')||{}).textContent||null;
    o.engFiles=(document.getElementById('engFiles')||{}).textContent||null;
    o.engTTS=(document.getElementById('engTTS')||{}).textContent||null;
    o.verLine=(document.getElementById('verLine')||{}).textContent||null;
    if (typeof switchTab==='function') { switchTab('home'); await sleep(300); }
    return o;
  })()`);

  /* ---- 8. TTS 檢測（WebView 內 speechSynthesis 的可用性與逾時） ---- */
  report.phases.tts = await evalIn(`(function(){
    const o = { hasSpeechSynthesis: ('speechSynthesis' in window) };
    try {
      o.voicesNow = speechSynthesis.getVoices().length;
      o.ttsVoiceChosen = !!(TTS && TTS.voice);
      o.ttsProbed = !!(TTS && TTS.probed);
      o.ttsVoiceName = (TTS && TTS.voice) ? TTS.voice.name + ' / ' + TTS.voice.lang : null;
    } catch(e) { o.err = String(e); }
    o.engTTSText = (document.getElementById('engTTS')||{}).textContent || null;
    o.ttsInfo = (document.getElementById('ttsInfo')||{}).textContent || null;
    return o;
  })()`, false);

} finally {
  try { ws.close(); } catch { }
  const uniq = [];
  for (const f of report.mp3) if (!uniq.includes(f)) uniq.push(f);
  report.mp3 = uniq;
  console.log(JSON.stringify(report, null, 1));
}
