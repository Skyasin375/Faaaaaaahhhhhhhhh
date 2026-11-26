# -*- coding: utf-8 -*-
"""
RBC GLORY - Bot Service and Real-Time EXP Dashboard
Embedded Async Web Server (aiohttp)
"""

import asyncio
import json
import hashlib
try:
    import orjson as _orjson
except Exception:
    _orjson = None
import os
import time
from collections import deque  # ✅ CRASH FIX: logs-এর জন্য O(1) deque — list.pop(0) ছিল O(n)

# Account level eta ba tar beshi hole BR theke automatic Lone Wolf. 0 dile bondho.
try:
    AUTO_LW_LEVEL = int(os.environ.get("AUTO_LW_LEVEL", "3"))
except Exception:
    AUTO_LW_LEVEL = 3
from typing import Dict, List, Any, Optional
from aiohttp import web

# ==================== BASE DIRECTORY (ALWAYS ABSOLUTE) ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ✅ AUTO MULTI-FILE SUPPORT - accounts.json, accounts2.json, accounts3.json ...
import glob as _glob
import fnmatch as _fnmatch

def get_all_account_files_dashboard():
    """Root-এ accounts*.json সব ফাইল অটো ডিটেক্ট করে"""
    files = sorted(_glob.glob(os.path.join(BASE_DIR, "accounts*.json")))
    if not files:
        files = [os.path.join(BASE_DIR, "accounts.json")]
    return files

ACCOUNTS_FILE_PATH = os.path.join(BASE_DIR, "accounts.json")  # default for new adds
# ✅ Complete (EXP/Level limit) বা Error (login fail) হওয়া আইডি এই ফাইলে জমা হয়।
# নাম "accounts*.json" প্যাটার্নে পড়ে না, তাই বট এটাকে সাধারণ accounts ফাইল ভেবে লোড করবে না।
DELETED_ACCOUNTS_FILE = os.path.join(BASE_DIR, "delete_accounts.json")

# ==================== EMBEDDED HTML DASHBOARD ====================
# Frontend is loaded from templates/index.html.
DASHBOARD_TEMPLATE = os.path.join(BASE_DIR, "templates", "index.html")


# ==================== LOGIN / ACCESS KEY ====================
# Dashboard-e dhukte Access Key lagbe. Default key: RBC_ADMIN
# Railway-te alada key chaile Variables-e DASHBOARD_KEY set korun (code change lagbe na).
import hmac as _hmac
import hashlib as _hashlib
import base64 as _b64

# ✅ ROLES: Admin = সব কাজ | User = শুধু দেখা + Add Account
#   Admin key  → ADMIN_KEY (না থাকলে DASHBOARD_KEY, ডিফল্ট RBC_ADMIN)
#   User key   → USER_KEY  (ডিফল্ট RBC_USER)
DASHBOARD_KEY = (os.environ.get("ADMIN_KEY") or os.environ.get("DASHBOARD_KEY") or "RBC_ADMIN").strip()
USER_KEY = (os.environ.get("USER_KEY") or "RBC_USER").strip()
USER_ALLOWED_PATHS = {"/", "/api/stats", "/api/account/add", "/api/logout"}
SESSION_COOKIE = "rbc_session"
SESSION_DAYS = 30
_SESSION_SECRET = _hashlib.sha256(("rbc-glory-dashboard|" + DASHBOARD_KEY + "|" + USER_KEY).encode("utf-8")).digest()
_LOGIN_FAILS: Dict[str, Any] = {}   # ip -> {"n": fail_count, "until": lock_until_ts}
_MAX_FAILS = 5
_LOCK_SECONDS = 60


LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0a0d12">
<title>RBC GLORY — Access</title>
<link rel="icon" href="#">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap"></noscript>
<style>
:root{--bg:#000;--gold:#f5b82e;--gold2:#ffd166;--green:#1ed760;--red:#ef4444;--text:#e6eaf0;--muted:#5a5a6a;--card-bg:rgba(10,10,12,.92)}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{font-family:'DM Sans','Segoe UI',system-ui,sans-serif;background:#000;color:var(--text);-webkit-font-smoothing:antialiased;overflow:hidden}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
background:radial-gradient(ellipse 80% 60% at 50% 100%,rgba(245,184,46,.13),transparent 65%),radial-gradient(ellipse 60% 40% at 50% 0%,rgba(30,215,96,.07),transparent 60%)}
body::after{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
background-image:linear-gradient(rgba(245,184,46,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(245,184,46,.03) 1px,transparent 1px);
background-size:38px 38px;-webkit-mask-image:radial-gradient(ellipse at 50% 50%,#000 10%,transparent 72%);mask-image:radial-gradient(ellipse at 50% 50%,#000 10%,transparent 72%)}
#fx{position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}
.scan{position:fixed;left:0;right:0;height:180px;top:-180px;pointer-events:none;z-index:1;
background:linear-gradient(180deg,transparent,rgba(245,184,46,.04),transparent);animation:scan 8s linear infinite}
@keyframes scan{to{transform:translateY(calc(100vh + 360px))}}

.wrap{position:relative;z-index:2;min-height:100%;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:24px 18px;overflow-y:auto}
.card{position:relative;width:min(400px,100%);padding:90px 28px 28px;margin-top:70px;border-radius:28px;text-align:center;
background:linear-gradient(170deg,rgba(16,16,18,.96),rgba(8,8,10,.98));
border:1px solid rgba(245,184,46,.18);
box-shadow:0 0 0 1px rgba(245,184,46,.06) inset,0 40px 100px rgba(0,0,0,.85),0 0 60px rgba(245,184,46,.06);
backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);
animation:rise .9s cubic-bezier(.22,1,.36,1) both}
@keyframes rise{from{opacity:0;transform:translateY(28px) scale(.96)}to{opacity:1;transform:none}}
.card::before{content:'';position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,var(--gold),var(--green),var(--gold),transparent)}
.card::after{content:'';position:absolute;bottom:0;left:20%;right:20%;height:1px;background:linear-gradient(90deg,transparent,rgba(245,184,46,.3),transparent)}
.corner{position:absolute;width:18px;height:18px;border:1.5px solid rgba(245,184,46,.5)}
.c1{top:10px;left:10px;border-right:0;border-bottom:0;border-top-left-radius:8px}
.c2{top:10px;right:10px;border-left:0;border-bottom:0;border-top-right-radius:8px}
.c3{bottom:10px;left:10px;border-right:0;border-top:0;border-bottom-left-radius:8px}
.c4{bottom:10px;right:10px;border-left:0;border-top:0;border-bottom-right-radius:8px}

.logo{position:absolute;left:50%;top:0;width:144px;height:144px;transform:translate(-50%,-50%);border-radius:50%;padding:3px;z-index:10}
.logo::before{content:'';position:absolute;inset:0;border-radius:50%;
background:conic-gradient(from 0deg,var(--gold),var(--green),var(--gold2),#111,var(--gold));
animation:spin 4s linear infinite}
.logo::after{content:'';position:absolute;inset:-18px;border-radius:50%;
background:radial-gradient(circle,rgba(245,184,46,.3),rgba(30,215,96,.12) 45%,transparent 70%);
filter:blur(16px);z-index:-1;animation:breathe 3s ease-in-out infinite}
.logo img{position:relative;z-index:1;width:100%;height:100%;border-radius:50%;display:block;background:#000;border:3px solid #000;object-fit:cover}
.logo-glow{position:absolute;left:50%;top:0;width:144px;height:144px;transform:translate(-50%,-50%);border-radius:50%;
background:radial-gradient(circle,rgba(245,184,46,.22),transparent 65%);filter:blur(20px);z-index:9;animation:breathe 3s ease-in-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes breathe{0%,100%{opacity:.6;transform:scale(.94)}50%{opacity:1;transform:scale(1.08)}}

h1{font-family:'Rajdhani','Segoe UI',sans-serif;font-size:32px;font-weight:700;letter-spacing:.18em;line-height:1;
background:linear-gradient(90deg,var(--gold),#fff,var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.sub{margin-top:10px;font-size:10px;letter-spacing:.38em;color:var(--muted);text-transform:uppercase;font-weight:600}
.lock-line{display:flex;align-items:center;gap:10px;margin:22px 0 16px;color:var(--muted);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase}
.lock-line::before,.lock-line::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(245,184,46,.3))}
.lock-line::after{transform:scaleX(-1)}

form{text-align:left}
label{display:block;font-family:'Rajdhani','Segoe UI',sans-serif;font-size:10.5px;font-weight:700;letter-spacing:.2em;color:rgba(245,184,46,.7);margin-bottom:8px;text-transform:uppercase}
.field{position:relative;display:flex;align-items:center;height:52px;background:rgba(245,184,46,.03);border:1px solid rgba(245,184,46,.18);border-radius:14px;transition:border-color .25s,box-shadow .25s}
.field:focus-within{border-color:rgba(245,184,46,.55);box-shadow:0 0 0 4px rgba(245,184,46,.08),0 0 30px rgba(245,184,46,.1)}
.field svg{flex:0 0 auto}
.field .ico{width:18px;height:18px;margin-left:15px;color:rgba(245,184,46,.45);transition:color .2s}
.field:focus-within .ico{color:var(--gold)}
.field input{flex:1;min-width:0;height:100%;padding:0 10px 0 12px;background:transparent;border:0;outline:0;color:var(--text);font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:16px;letter-spacing:.22em;text-transform:uppercase}
.field input::placeholder{letter-spacing:.1em;text-transform:none;color:#3a3a48;font-family:'DM Sans',sans-serif;font-size:14px}
.eye{width:44px;height:100%;background:none;border:0;color:var(--muted);cursor:pointer;display:grid;place-items:center;transition:color .2s}
.eye:hover{color:var(--gold)}.eye svg{width:19px;height:19px}
.err{min-height:20px;margin:9px 2px 0;font-size:12px;color:var(--red);font-weight:500}
.btn{position:relative;width:100%;height:52px;margin-top:8px;border:0;border-radius:14px;cursor:pointer;overflow:hidden;color:#000;
font-family:'Rajdhani','Segoe UI',sans-serif;font-size:16px;font-weight:700;letter-spacing:.18em;
display:flex;align-items:center;justify-content:center;gap:10px;
background:linear-gradient(100deg,var(--gold),var(--gold2),var(--gold));
box-shadow:0 8px 28px rgba(245,184,46,.28),0 0 0 1px rgba(245,184,46,.15) inset;
transition:transform .15s,box-shadow .2s,filter .2s}
.btn::after{content:'';position:absolute;top:0;bottom:0;width:60px;left:-80px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.5),transparent);transform:skewX(-20deg);transition:left .55s}
.btn:hover{transform:translateY(-2px);box-shadow:0 14px 40px rgba(245,184,46,.42)}.btn:hover::after{left:120%}
.btn:active{transform:scale(.98)}.btn:disabled{cursor:wait;filter:saturate(.6) brightness(.85)}
.btn svg{width:18px;height:18px;transition:transform .2s}.btn:hover svg{transform:translateX(4px)}
.spin{width:18px;height:18px;border:2.5px solid rgba(0,0,0,.25);border-top-color:#000;border-radius:50%;animation:spin .7s linear infinite}
.tag{margin-top:22px;display:flex;justify-content:center;align-items:center;gap:10px;font-size:10px;letter-spacing:.28em;color:var(--muted);font-weight:700;white-space:nowrap}
.tag i{width:3px;height:3px;border-radius:50%;background:var(--gold);opacity:.7}

/* ── SUCCESS OVERLAY ── */
.success-overlay{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;
background:rgba(0,0,0,.0);backdrop-filter:blur(0px);-webkit-backdrop-filter:blur(0px);
pointer-events:none;transition:background .4s ease,backdrop-filter .4s ease}
.success-overlay.show{background:rgba(0,0,0,.88);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);pointer-events:all}
.success-box{display:flex;flex-direction:column;align-items:center;gap:14px;opacity:0;transform:scale(.7) translateY(20px);transition:opacity .45s cubic-bezier(.22,1,.36,1),transform .45s cubic-bezier(.22,1,.36,1)}
.success-overlay.show .success-box{opacity:1;transform:scale(1) translateY(0)}
.success-ring{width:96px;height:96px;position:relative;filter:drop-shadow(0 0 18px rgba(30,215,96,.55))}
.success-check{width:100%;height:100%}
.check-circle{fill:none;stroke:var(--green);stroke-width:2.5;stroke-dasharray:152;stroke-dashoffset:152;animation:none}
.success-overlay.show .check-circle{animation:drawcircle .6s .15s cubic-bezier(.4,0,.2,1) forwards}
@keyframes drawcircle{to{stroke-dashoffset:0}}
.check-tick{fill:none;stroke:var(--green);stroke-width:3;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:40;stroke-dashoffset:40;animation:none}
.success-overlay.show .check-tick{animation:drawtick .35s .65s cubic-bezier(.4,0,.2,1) forwards}
@keyframes drawtick{to{stroke-dashoffset:0}}
.success-title{font-family:'Rajdhani','Segoe UI',sans-serif;font-size:28px;font-weight:700;letter-spacing:.22em;
background:linear-gradient(90deg,var(--gold),#fff,var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
opacity:0;transform:translateY(8px);transition:opacity .4s .8s ease,transform .4s .8s ease}
.success-overlay.show .success-title{opacity:1;transform:translateY(0)}
.success-sub{font-size:12px;letter-spacing:.18em;color:var(--muted);text-transform:uppercase;font-weight:600;
opacity:0;transition:opacity .4s 1s ease}
.success-overlay.show .success-sub{opacity:1}
.dots span{animation:blink 1.2s 1.1s infinite}
.dots span:nth-child(2){animation-delay:1.3s}.dots span:nth-child(3){animation-delay:1.5s}
@keyframes blink{0%,80%,100%{opacity:0}40%{opacity:1}}
.success-bar-wrap{width:220px;height:3px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden;
opacity:0;transition:opacity .3s 1.1s ease}
.success-overlay.show .success-bar-wrap{opacity:1}
.success-bar{height:100%;width:0;background:linear-gradient(90deg,var(--green),var(--gold));border-radius:99px;transition:width 1.6s 1.2s cubic-bezier(.4,0,.2,1)}
.success-bar.go{width:100%}
/* card fade out on success */
.card.success-fade{animation:cardfade .5s .3s cubic-bezier(.4,0,.2,1) forwards}
@keyframes cardfade{to{opacity:0;transform:scale(.92) translateY(-14px);filter:blur(6px)}}
.shake{animation:shake .5s cubic-bezier(.36,.07,.19,.97)}
@keyframes shake{10%,90%{transform:translateX(-2px)}20%,80%{transform:translateX(4px)}30%,50%,70%{transform:translateX(-7px)}40%,60%{transform:translateX(7px)}}
.card.ok{animation:ok .8s cubic-bezier(.22,1,.36,1) forwards;border-color:rgba(245,184,46,.6);box-shadow:0 0 60px rgba(245,184,46,.25)}
.card.ok .logo::before{animation-duration:.6s}
@keyframes ok{to{opacity:0;transform:scale(1.08) translateY(-12px);filter:blur(5px)}}
.flash{position:fixed;inset:0;z-index:5;pointer-events:none;background:radial-gradient(circle at 50% 40%,rgba(245,184,46,.22),rgba(30,215,96,.1) 50%,transparent 70%);opacity:0;transition:opacity .6s}
.flash.on{opacity:1}
@media(max-width:380px){.card{padding-left:18px;padding-right:18px}h1{font-size:26px}.tag{letter-spacing:.16em}}
@media(max-height:620px){.card{margin-top:76px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<canvas id="fx"></canvas>
<div class="scan"></div>
<div class="flash" id="flash"></div>

<!-- SUCCESS OVERLAY -->
<div class="success-overlay" id="successOverlay">
  <div class="success-box">
    <div class="success-ring">
      <svg class="success-check" viewBox="0 0 52 52"><circle class="check-circle" cx="26" cy="26" r="24"/><path class="check-tick" d="M14 26l8 8 16-16"/></svg>
    </div>
    <div class="success-title">ACCESS GRANTED</div>
    <div class="success-sub">Opening Dashboard<span class="dots"><span>.</span><span>.</span><span>.</span></span></div>
    <div class="success-bar-wrap"><div class="success-bar" id="successBar"></div></div>
  </div>
</div>

<div class="wrap">
  <main class="card" id="card">
    <i class="corner c1"></i><i class="corner c2"></i><i class="corner c3"></i><i class="corner c4"></i>
    <div class="logo-glow"></div>
    <div class="logo"><img src="" alt="RBC" width="140" height="140"></div>

    <h1>RBC GLORY</h1>
    <div class="sub">Free Fire · Bot Dashboard</div>
    <div class="lock-line">🔐 Enter Access Key</div>

    <form id="form" autocomplete="off">
      <label for="key">ACCESS KEY</label>
      <div class="field" id="field">
        <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3"/><path d="m16 7 3 3"/><path d="m14 9 2 2"/></svg>
        <input id="key" name="key" type="password" placeholder="Type your key" autocomplete="off" autocapitalize="characters" autocorrect="off" spellcheck="false" maxlength="64" required>
        <button class="eye" id="eye" type="button" aria-label="Show key">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
      </div>
      <div class="err" id="err" role="alert" aria-live="polite"></div>
      <button class="btn" id="btn" type="submit"><span id="btnTxt">UNLOCK DASHBOARD</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
      </button>
    </form>

    <div class="tag"><span>TRUSTED</span><i></i><span>FAST</span><i></i><span>ALWAYS</span></div>
  </main>
</div>

<script>
const $=id=>document.getElementById(id);
try{localStorage.removeItem('rbc_last')}catch(e){}
const card=$('card'),key=$('key'),err=$('err'),btn=$('btn'),btnTxt=$('btnTxt');
let busy=false,lockTimer=null;

function showSuccess(){
  /* 1. Card fade out */
  card.classList.add('success-fade');
  /* 2. Flash burst */
  $('flash').classList.add('on');
  /* 3. Show overlay */
  const ov=$('successOverlay');
  requestAnimationFrame(()=>{
    ov.classList.add('show');
    /* 4. Start progress bar after short delay */
    setTimeout(()=>$('successBar').classList.add('go'),300);
    /* 5. Redirect after animation completes */
    setTimeout(()=>location.replace('/'),2800);
  });
}

$('eye').addEventListener('click',()=>{const show=key.type==='password';key.type=show?'text':'password';$('eye').setAttribute('aria-label',show?'Hide key':'Show key');key.focus()});
key.addEventListener('input',()=>{err.textContent=''});

function fail(msg){
  err.textContent=msg;
  card.classList.remove('shake');void card.offsetWidth;card.classList.add('shake');
  key.select();
}
function startLock(sec){
  clearInterval(lockTimer);
  btn.disabled=true;
  const tick=()=>{if(sec<=0){clearInterval(lockTimer);btn.disabled=false;err.textContent='';btnTxt.textContent='UNLOCK DASHBOARD';return}
    btnTxt.textContent='LOCKED · '+sec+'s';err.textContent='Too many wrong attempts. Please wait.';sec--};
  tick();lockTimer=setInterval(tick,1000);
}

$('form').addEventListener('submit',async e=>{
  e.preventDefault();
  const v=key.value.trim();
  if(busy||btn.disabled)return;
  if(!v){fail('Please enter your access key.');return}
  busy=true;btn.disabled=true;err.textContent='';
  const old=btn.innerHTML;btn.innerHTML='<span class="spin"></span><span>VERIFYING…</span>';
  try{
    const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:v}),credentials:'same-origin'});
    const d=await r.json().catch(()=>({}));
    if(r.ok&&d.status==='ok'){
      showSuccess();
      return;
    }
    btn.innerHTML=old;busy=false;
    if(r.status===429){startLock(Math.max(1,Math.ceil(d.retry_after||60)));return}
    btn.disabled=false;fail(d.error||'Wrong access key. Try again.');
  }catch(ex){
    btn.innerHTML=old;busy=false;btn.disabled=false;fail('Cannot reach the server. Check your connection.');
  }
});
key.focus();

/* ember particles */
(function(){
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const c=$('fx'),x=c.getContext('2d');let W,H,dpr,P=[];
  function size(){dpr=Math.min(devicePixelRatio||1,2);W=innerWidth;H=innerHeight;c.width=W*dpr;c.height=H*dpr;x.setTransform(dpr,0,0,dpr,0,0)}
  function mk(init){const g=Math.random();return{x:Math.random()*W,y:init?Math.random()*H:H+10,r:Math.random()*2+.4,v:Math.random()*.55+.2,d:(Math.random()-.5)*.3,a:Math.random()*.6+.2,h:g<.55?'245,184,46':g<.8?'30,215,96':'255,255,255',t:Math.random()*6.28}}
  size();addEventListener('resize',size);
  const N=Math.round(Math.min(70,Math.max(28,W*H/20000)));
  for(let i=0;i<N;i++)P.push(mk(true));
  (function loop(){
    x.clearRect(0,0,W,H);
    for(const p of P){
      p.y-=p.v;p.t+=.02;p.x+=p.d+Math.sin(p.t)*.25;
      if(p.y<-10)Object.assign(p,mk(false));
      const al=p.a*Math.min(1,p.y/(H*.35));
      x.beginPath();x.fillStyle='rgba('+p.h+','+Math.max(0,al)+')';x.shadowColor='rgba('+p.h+',.9)';x.shadowBlur=8;
      x.arc(p.x,p.y,p.r,0,6.283);x.fill();
    }
    requestAnimationFrame(loop);
  })();
})();
</script>
</body>
</html>
"""


def _make_session_token(role: str = "admin") -> str:
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    sig = _hmac.new(_SESSION_SECRET, f"{role}|{exp}".encode(), _hashlib.sha256).hexdigest()
    return f"{role}.{exp}.{sig}"


def _token_role(token: Optional[str]) -> Optional[str]:
    """সঠিক টোকেন হলে role ('admin' / 'user') ফেরত দেয়, নইলে None"""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    role, exp, sig = parts
    if role not in ("admin", "user") or not exp.isdigit() or int(exp) < time.time():
        return None
    good = _hmac.new(_SESSION_SECRET, f"{role}|{exp}".encode(), _hashlib.sha256).hexdigest()
    return role if _hmac.compare_digest(sig, good) else None


def _client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote or "?"


def _is_https(request: web.Request) -> bool:
    return request.secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"


def _session_role(request: web.Request) -> Optional[str]:
    return _token_role(request.cookies.get(SESSION_COOKIE))


def _is_authed(request: web.Request) -> bool:
    return _session_role(request) is not None


# ✅ OWNER ID: প্রতিটি User ব্রাউজারের আলাদা পরিচয় (লগআউট করলেও থাকে) — নিজের যোগ করা আইডি চিনতে লাগে
import secrets as _secrets
OWNER_COOKIE = "rbc_owner"


def _sign_owner(oid: str) -> str:
    return _hmac.new(_SESSION_SECRET, ("owner|" + oid).encode(), _hashlib.sha256).hexdigest()[:24]


def _owner_id(request: web.Request) -> Optional[str]:
    raw = request.cookies.get(OWNER_COOKIE, "")
    oid, _, sig = raw.partition(".")
    if oid and sig and _hmac.compare_digest(sig, _sign_owner(oid)):
        return oid
    return None


def _owner_cookie_value(oid: str) -> str:
    return f"{oid}.{_sign_owner(oid)}"


@web.middleware
async def auth_middleware(request: web.Request, handler):
    path = request.path
    if path in ("/login", "/api/login", "/favicon.ico", "/healthz"):
        return await handler(request)
    role = _session_role(request)
    if role:
        request["role"] = role
        # User শুধু দেখতে ও Add Account করতে পারবে — বাকি সব API সার্ভারেই আটকানো
        if role == "user" and path not in USER_ALLOWED_PATHS:
            if path.startswith("/api/"):
                return web.json_response({"status": "error", "error": "Admin access only"}, status=403)
            raise web.HTTPFound("/")
        try:
            return await handler(request)
        finally:
            if request.method == "POST":
                _STATS_CACHE.clear()   # action-এর পরে ক্যাশ মুছো → dashboard সাথে সাথে নতুন data দেখায়
    if path.startswith("/api/"):
        return web.json_response({"status": "error", "error": "unauthorized"}, status=401)
    raise web.HTTPFound("/login")


@web.middleware
async def compress_middleware(request: web.Request, handler):
    resp = await handler(request)
    try:
        if (isinstance(resp, web.Response) and resp.status != 304 and "Content-Encoding" not in resp.headers and request.path != "/healthz"):
            resp.enable_compression()
    except Exception:
        pass
    return resp


async def handle_login_page(request: web.Request) -> web.Response:
    if _is_authed(request):
        raise web.HTTPFound("/")
    return web.Response(text=LOGIN_HTML, content_type="text/html", charset="utf-8",
                        headers={"Cache-Control": "no-store"})



async def handle_login(request: web.Request) -> web.Response:
    ip = _client_ip(request)
    now = time.time()
    rec = _LOGIN_FAILS.get(ip, {"n": 0, "until": 0})
    if rec["until"] > now:
        return web.json_response(
            {"status": "error", "error": "Too many attempts", "retry_after": int(rec["until"] - now) + 1},
            status=429)
    try:
        data = await request.json()
    except Exception:
        data = {}
    supplied = str(data.get("key", "")).strip()
    # case-insensitive, constant-time compare
    sup = supplied.upper().encode("utf-8")
    role = None
    if _hmac.compare_digest(sup, DASHBOARD_KEY.upper().encode("utf-8")):
        role = "admin"
    elif _hmac.compare_digest(sup, USER_KEY.upper().encode("utf-8")):
        role = "user"
    if role is None:
        rec["n"] = rec.get("n", 0) + 1
        if rec["n"] >= _MAX_FAILS:
            rec = {"n": 0, "until": now + _LOCK_SECONDS}
            _LOGIN_FAILS[ip] = rec
            return web.json_response(
                {"status": "error", "error": "Too many attempts", "retry_after": _LOCK_SECONDS}, status=429)
        _LOGIN_FAILS[ip] = rec
        left = _MAX_FAILS - rec["n"]
        return web.json_response(
            {"status": "error", "error": f"Wrong access key. {left} attempt(s) left."}, status=401)
    _LOGIN_FAILS.pop(ip, None)
    resp = web.json_response({"status": "ok", "role": role})
    if role == "user" and not _owner_id(request):
        resp.set_cookie(OWNER_COOKIE, _owner_cookie_value(_secrets.token_hex(6)), max_age=365 * 86400,
                        httponly=True, samesite="Lax", secure=_is_https(request), path="/")
    resp.set_cookie(SESSION_COOKIE, _make_session_token(role), max_age=SESSION_DAYS * 86400,
                    httponly=True, samesite="Lax", secure=_is_https(request), path="/")
    return resp


async def handle_logout(request: web.Request) -> web.Response:
    resp = web.json_response({"status": "ok"})
    resp.del_cookie(SESSION_COOKIE, path="/")
    return resp


# Global bot state shared between app.py and Web Dashboard
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        # ✅ CRASH FIX: deque(maxlen=200) → O(1) append+auto-drop, list.pop(0) ছিল O(n)
        # 200 account heavy logging-এ list ধীরে ধীরে সব CPU খেয়ে ফেলত
        self.logs: deque = deque(maxlen=200)
        self.max_logs = 200  # deque maxlen-এর সাথে মিলিয়ে রাখা
        self.total_matches = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}
        # ✅ DELETE করা UID গুলো ব্ল্যাকলিস্টে রাখা হয়
        # যাতে চলমান worker পুনরায় register করতে না পারে
        # ✅ FIX: এখন ডিস্কে সেভ হয় — redeploy-এর পরেও টিকে থাকে
        self.deleted_uids_file = os.path.join(BASE_DIR, "deleted_uids.json")
        self.deleted_uids: set = set()
        self._load_deleted_uids()
        # ✅ প্রতিটি UID-এর জন্য আলাদা match type — "BR" বা "LONE_WOLF"
        self.match_types: Dict[str, str] = {}
        # ✅ Global mode: ডিফল্ট AUTO — নতুন আইডি যোগ হলে বা restart হলে সবসময় AUTO
        self.global_mode: str = "AUTO"
        # ✅ Global ON/OFF — False হলে কোনো আইডি match search করবে না
        self.global_running: bool = True
        # ✅ AUTO-DELETE: gained_exp এই লিমিট পার হলে আইডি অটো ডিলিট হবে
        self.exp_limit: int = 0  # ডিফল্ট 0 — dashboard থেকে সেট করুন
        # ✅ AUTO-DELETE queue: async cleanup-এর জন্য
        self.auto_delete_queue: set = set()
        # ✅ LEVEL LIMIT: আইডির level এই সংখ্যায় পৌঁছালে dashboard থেকে সরে যাবে (0 = বন্ধ)
        # EXP লিমিটের মতোই accounts.json থেকেও স্থায়ীভাবে মুছে যাবে
        self.level_limit: int = 0
        self.level_remove_queue: set = set()
        # ✅ config-এর guest UID → login-এর পর real account id (app.py সেট করে)
        self.guest_alias: Dict[str, str] = {}
        # ✅ OWNERS: config key (guest UID বা tok_xxxx) → যে User যোগ করেছে তার owner id
        self.owners_file = os.path.join(BASE_DIR, "account_owners.json")
        self.account_owner: Dict[str, str] = {}
        self._load_owners()
        # ✅ USER ADD LIMIT: Admin ঠিক করে প্রতিটি User সর্বোচ্চ কয়টি আইডি রাখতে পারবে (0 = সীমাহীন)
        self.settings_file = os.path.join(BASE_DIR, "dashboard_settings.json")
        self.user_add_limit: int = 0
        # ✅ AUTO-RESTART: ৬ ঘন্টা পর অটো অফলাইন → ১০ মিনিট বিরতি → আবার কানেক্ট
        self.auto_restart_enabled: bool = False
        self.auto_restart_interval_hours: float = 1.5  # ✅ FIXED: 1h 30min পর offline
        self.auto_restart_break_minutes: int = 10      # কত মিনিট offline থাকবে
        self._auto_restart_task: Optional[asyncio.Task] = None
        self._auto_restart_phase: str = ""             # "", "running", "break", "reconnecting"
        self._auto_restart_next_ts: float = 0.0        # পরবর্তী ঘটনার timestamp
        self._load_settings()
        # ✅ LOGIN FAIL AUTO-REMOVE: পর পর MAX_LOGIN_FAILS বার login fail হলে আইডি dashboard থেকে সরে যাবে
        self.login_fail_counts: Dict[str, int] = {}
        self.MAX_LOGIN_FAILS: int = int(os.environ.get("MAX_LOGIN_FAILS", "5"))

    def set_match_type(self, uid: str, match_type: str):
        """Dashboard থেকে UID-এর match type সেট করা: শুধু 'BR_EVO'"""
        uid_str = str(uid)
        allowed = {"BR", "LONE_WOLF", "LW_HS", "BR_EVO"}
        if match_type not in allowed:
            match_type = "BR_EVO"
        self.match_types[uid_str] = match_type
        if uid_str in self.accounts:
            self.accounts[uid_str]["match_type"] = match_type
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def set_auto_all(self):
        """সব আইডিকে AUTO (Level-based) মোডে ফেরানো এবং global_mode = AUTO"""
        self.global_mode = "AUTO"
        for uid_str in list(self.accounts.keys()):
            self.match_types.pop(uid_str, None)
            lvl = self.get_account_level(uid_str)
            self.accounts[uid_str]["match_type"] = "BR_EVO"

    def get_match_type(self, uid: str) -> str:
        """UID-এর বর্তমান match type — সবসময় BR_EVO (Dashboard Bear EVO)"""
        uid_str = str(uid)
        return self.match_types.get(uid_str, "BR_EVO")

    async def _async_auto_delete(self, uid_str: str):
        """45000 EXP পূর্ণ হওয়া আইডির async cleanup: worker cancel + JSON ফাইল থেকে মুছে ফেলা"""
        try:
            short_key = uid_str.replace("tok_", "")[:10]

            # ✅ STEP 1: bot_state থেকে সরাও
            self.accounts.pop(uid_str, None)
            self.recalc_totals()

            # ✅ STEP 2: accounts*.json ফাইল থেকে atomic delete
            for accounts_file in get_all_account_files_dashboard():
                if not os.path.exists(accounts_file):
                    continue
                try:
                    with open(accounts_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if not isinstance(existing, list):
                        continue
                    new_list = [
                        acc for acc in existing
                        if str(acc.get("uid", "")).strip() not in self._json_ids(uid_str)
                        and str(acc.get("token", ""))[:10] != short_key
                    ]
                    if len(new_list) < len(existing):
                        tmp_file = accounts_file + ".tmp"
                        with open(tmp_file, "w", encoding="utf-8") as f:
                            json.dump(new_list, f, indent=2, ensure_ascii=False)
                        os.replace(tmp_file, accounts_file)
                except Exception:
                    pass

            # ✅ STEP 3: Worker task বাতিল করো
            for worker_key in [uid_str, short_key]:
                if worker_key in self.account_workers:
                    task = self.account_workers.pop(worker_key)
                    task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass

            self.auto_delete_queue.discard(uid_str)
            self.log(f"[AUTO-DELETE] UID {uid_str} → 45000 EXP লিমিট পূর্ণ। আইডি সম্পূর্ণরূপে মুছে ফেলা হয়েছে।", "warning", uid_str)
        except Exception as e:
            self.log(f"[AUTO-DELETE ERROR] UID {uid_str}: {e}", "error", uid_str)

    def _load_deleted_uids(self):
        """redeploy-এর পরেও deleted/level-limit আইডি blacklist-এ থাকবে"""
        try:
            if os.path.exists(self.deleted_uids_file):
                with open(self.deleted_uids_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.deleted_uids = set(str(u) for u in data)
        except Exception:
            self.deleted_uids = set()

    def _save_deleted_uids(self):
        """deleted_uids ডিস্কে সেভ — atomic write"""
        try:
            tmp = self.deleted_uids_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(list(self.deleted_uids), f, ensure_ascii=False)
            os.replace(tmp, self.deleted_uids_file)
        except Exception:
            pass

    def _load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self.user_add_limit = max(0, int(d.get("user_add_limit", 0) or 0))
                    # ✅ FIX: রিডিপ্লয়ের পরেও exp_limit ও level_limit টিকে থাকবে
                    saved_exp = d.get("exp_limit", None)
                    if saved_exp is not None:
                        self.exp_limit = max(0, int(saved_exp or 0))
                    saved_lv = d.get("level_limit", None)
                    if saved_lv is not None:
                        self.level_limit = max(0, int(saved_lv or 0))
                    # ✅ AUTO-RESTART settings persist
                    self.auto_restart_enabled = bool(d.get("auto_restart_enabled", False))
                    self.auto_restart_interval_hours = max(0.5, float(d.get("auto_restart_interval_hours", 1.5) or 1.5))
                    self.auto_restart_break_minutes = max(1, int(d.get("auto_restart_break_minutes", 10) or 10))
        except Exception:
            self.user_add_limit = 0

    def _save_settings(self):
        try:
            tmp = self.settings_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "user_add_limit": self.user_add_limit,
                    "exp_limit": self.exp_limit,       # ✅ FIX: persist
                    "level_limit": self.level_limit,   # ✅ FIX: persist
                    "auto_restart_enabled": self.auto_restart_enabled,
                    "auto_restart_interval_hours": self.auto_restart_interval_hours,
                    "auto_restart_break_minutes": self.auto_restart_break_minutes,
                }, f, indent=2)
            os.replace(tmp, self.settings_file)
        except Exception:
            pass

    def count_user_ids(self, owner: str, existing: list) -> int:
        """এই User-এর যোগ করা আইডি, যেগুলো এখনো accounts.json-এ আছে (অটো-ডিলিট/ডিলিট হলে সংখ্যা কমে)"""
        present = set()
        for acc in existing:
            if not isinstance(acc, dict):
                continue
            if acc.get("uid") is not None:
                present.add(str(acc.get("uid")))
            if acc.get("token"):
                present.add("tok_" + str(acc["token"])[:10])
        return sum(1 for k, v in self.account_owner.items() if v == owner and k in present)

    def _load_owners(self):
        try:
            if os.path.exists(self.owners_file):
                with open(self.owners_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self.account_owner = {str(k): str(v) for k, v in d.items()}
        except Exception:
            self.account_owner = {}

    def _save_owners(self):
        try:
            tmp = self.owners_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.account_owner, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.owners_file)
        except Exception:
            pass

    def owner_of(self, key: str) -> Optional[str]:
        """ড্যাশবোর্ড key (guest হলে login-এর পর real id) থেকে মালিক খোঁজে"""
        key = str(key)
        o = self.account_owner.get(key)
        if o:
            return o
        for guest, real in self.guest_alias.items():
            if real == key and guest in self.account_owner:
                return self.account_owner[guest]
        return None

    def _json_ids(self, uid_str: str) -> set:
        """accounts.json-এ এই আইডি যে নামে আছে (guest UID হলে login-এর আগের UID-ও)"""
        ids = {uid_str}
        for guest, real in self.guest_alias.items():
            if real == uid_str:
                ids.add(guest)
        return ids

    def _remove_from_json(self, uid_str: str, reason: Optional[str] = None):
        """accounts*.json থেকে আইডি সরায় (atomic write)।
        reason দিলে ("complete" / "error") সরানো এন্ট্রি delete_accounts.json-এ জমা হয়।"""
        short_key = uid_str.replace("tok_", "")[:10]
        ids = self._json_ids(uid_str)
        archived = []
        for accounts_file in get_all_account_files_dashboard():
            if not os.path.exists(accounts_file):
                continue
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    continue
                new_list, removed = [], []
                for acc in existing:
                    hit = (isinstance(acc, dict)
                           and (str(acc.get("uid", "")).strip() in ids
                                or str(acc.get("token", ""))[:10] == short_key))
                    (removed if hit else new_list).append(acc)
                if removed:
                    tmp_file = accounts_file + ".tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(new_list, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_file, accounts_file)
                    for acc in removed:
                        archived.append((acc, os.path.basename(accounts_file)))
            except Exception:
                pass
        if reason and archived:
            self._archive_deleted(archived, uid_str, reason)

    # ---------- delete_accounts.json (complete / error আইডির আর্কাইভ) ----------
    def _read_deleted_file(self) -> list:
        try:
            if os.path.exists(DELETED_ACCOUNTS_FILE):
                with open(DELETED_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
        except Exception:
            pass
        return []

    def _write_deleted_file(self, items: list):
        tmp = DELETED_ACCOUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, DELETED_ACCOUNTS_FILE)

    @staticmethod
    def _entry_key(acc: dict) -> str:
        if acc.get("token"):
            return "tok_" + str(acc["token"])[:10]
        return str(acc.get("uid", "")).strip()

    def _archive_deleted(self, archived: list, dashboard_id: str, reason: str):
        """সরানো আইডিগুলো delete_accounts.json-এ যোগ করে (duplicate হবে না)"""
        try:
            items = self._read_deleted_file()
            have = {self._entry_key(i) for i in items}
            for acc, src in archived:
                if self._entry_key(acc) in have:
                    continue
                rec = dict(acc)
                rec["_dashboard_id"] = dashboard_id          # real account id (restore-এর সময় blacklist পরিষ্কারে লাগে)
                rec["_reason"] = reason                      # "complete" বা "error"
                rec["_source_file"] = src
                rec["_removed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                items.append(rec)
                have.add(self._entry_key(acc))
            self._write_deleted_file(items)
        except Exception as e:
            self.log(f"[ARCHIVE ERROR] {dashboard_id}: {e}", "error", dashboard_id)

    def deleted_file_count(self) -> int:
        return len(self._read_deleted_file())

    def restore_deleted_accounts(self) -> int:
        """delete_accounts.json-এর সব আইডি আবার accounts*.json-এ ফেরত দেয়, blacklist থেকে সরায়,
        এবং ফাইল খালি করে। ফেরত দেয়: কয়টি আইডি ফিরেছে।"""
        items = self._read_deleted_file()
        if not items:
            return 0
        by_file: Dict[str, list] = {}
        for rec in items:
            src = os.path.basename(str(rec.get("_source_file") or "accounts.json"))
            if not _fnmatch.fnmatch(src, "accounts*.json"):
                src = "accounts.json"
            clean = {k: v for k, v in rec.items() if not str(k).startswith("_")}
            by_file.setdefault(src, []).append(clean)
            # blacklist ও কাউন্টার থেকে সব সম্ভাব্য key সরাও
            keys = {str(rec.get("_dashboard_id") or ""), self._entry_key(clean),
                    str(clean.get("uid", "")).strip()}
            if clean.get("token"):
                keys.add(str(clean["token"])[:10])
            real = self.guest_alias.get(str(clean.get("uid", "")).strip())
            if real:
                keys.add(real)
            for k in keys:
                if not k:
                    continue
                self.deleted_uids.discard(k)
                self.level_remove_queue.discard(k)
                self.auto_delete_queue.discard(k)
                self.login_fail_counts.pop(k, None)
        restored = 0
        for src, entries in by_file.items():
            fp = os.path.join(BASE_DIR, src)
            try:
                existing = []
                if os.path.exists(fp):
                    with open(fp, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if isinstance(d, list):
                        existing = d
                have = {self._entry_key(a) for a in existing if isinstance(a, dict)}
                for e in entries:
                    if self._entry_key(e) not in have:
                        existing.append(e)
                        have.add(self._entry_key(e))
                    restored += 1
                tmp = fp + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)
                os.replace(tmp, fp)
            except Exception as e:
                self.log(f"[RESTORE ERROR] {src}: {e}", "error")
        self._save_deleted_uids()
        self._write_deleted_file([])
        return restored

    async def _async_level_remove(self, uid_str: str):
        """Level লিমিট পূর্ণ হলে: শুধু worker বন্ধ করা।
        accounts ও JSON check_level_limit()-এই synchronously মুছে ফেলা হয়েছে।"""
        try:
            short_key = uid_str.replace("tok_", "")[:10]
            # ✅ accounts & JSON ইতিমধ্যে check_level_limit()-এ মুছে ফেলা হয়েছে
            # শুধু worker task cancel করতে হবে
            for worker_key in [uid_str, short_key]:
                if worker_key in self.account_workers:
                    task = self.account_workers.pop(worker_key)
                    task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass
            self.log(f"[LEVEL-LIMIT] UID {uid_str} → worker বন্ধ করা হয়েছে।", "warning", uid_str)
        except Exception as e:
            self.log(f"[LEVEL-LIMIT ERROR] UID {uid_str}: {e}", "error", uid_str)
        finally:
            self.level_remove_queue.discard(uid_str)

    def check_level_limit(self, uid_str: str):
        """আইডির level লিমিটে পৌঁছালে সাথে সাথে blacklist করে সরিয়ে দেয়"""
        if self.level_limit <= 0 or uid_str in self.level_remove_queue or uid_str in self.deleted_uids:
            return
        acc = self.accounts.get(uid_str)
        if not acc:
            return
        try:
            lv = int(acc.get("level", 1) or 1)
        except (ValueError, TypeError):
            return
        if lv >= self.level_limit:
            self.level_remove_queue.add(uid_str)
            self.deleted_uids.add(uid_str)      # reload না চাপা পর্যন্ত আর register/start হবে না
            self._save_deleted_uids()           # ✅ FIX: redeploy-এর পরেও blacklist টিকে থাকবে
            self.match_types.pop(uid_str, None)

            # ✅ FIX: Dashboard থেকে সাথে সাথে (synchronously) মুছে ফেলো।
            # আগে শুধু async task-এর উপর নির্ভর করত — task fail হলে account
            # "Offline" হয়ে dashboard-এ রয়ে যেত। এখন এখানেই মুছে যাবে।
            self.accounts.pop(uid_str, None)
            self.recalc_totals()
            self._remove_from_json(uid_str, "complete")     # accounts.json থেকে সরিয়ে delete_accounts.json-এ রাখো
            self.log(
                f"[LEVEL-LIMIT] UID {uid_str} → Lv{lv} (লিমিট: Lv{self.level_limit})। "
                f"আইডি dashboard ও accounts.json থেকে সরিয়ে delete_accounts.json-এ রাখা হয়েছে।",
                "warning", uid_str
            )
            # Worker cancel async-এ করা হবে
            try:
                # ✅ CRASH FIX: get_event_loop() → get_running_loop() — Python 3.12-এ safe
                asyncio.get_running_loop().create_task(self._async_level_remove(uid_str))
            except RuntimeError:
                # Event loop না থাকলেও কোনো সমস্যা নেই — account ইতিমধ্যে মুছে গেছে
                self.level_remove_queue.discard(uid_str)

    def enforce_level_limit(self):
        """লিমিট সেট/পরিবর্তনের সময় চলমান সব আইডি যাচাই"""
        for uid_str in list(self.accounts.keys()):
            self.check_level_limit(uid_str)

    def get_account_level(self, uid: str) -> int:
        """UID-এর current level পড়া — default 1"""
        uid_str = str(uid)
        if uid_str in self.accounts:
            return int(self.accounts[uid_str].get("level", 1) or 1)
        return 1

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": uid
        }
        self.logs.append(entry)  # ✅ deque(maxlen=200) স্বয়ংক্রিয়ভাবে পুরনো entry ফেলে দেয়

    def preload_pending(self) -> int:
        """accounts*.json পড়ে সাথে সাথে 'Connecting' কার্ড দেখায় — লগইন শেষ হওয়ার অপেক্ষা নেই"""
        n = 0
        try:
            for fp in get_all_account_files_dashboard():
                if not os.path.exists(fp):
                    continue
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                if not isinstance(data, list):
                    continue
                for acc in data:
                    if not isinstance(acc, dict) or not acc.get("uid"):
                        continue
                    key = str(acc["uid"]).strip()
                    if not key or key in self.deleted_uids or key in self.accounts:
                        continue
                    # আগেই লগইন হয়ে গেলে (alias) আবার placeholder নয়
                    real = self.guest_alias.get(key)
                    if real and real in self.accounts:
                        continue
                    self.accounts[key] = {
                        "uid": key, "nickname": f"Player_{key[:6]}", "region": "BD",
                        "level": 0, "initial_exp": 0, "current_exp": 0, "gained_exp": 0,
                        "likes": 0, "status": "CONNECTING", "matches_played": 0,
                        "active_matches": 0, "last_match_time": None,
                        "last_updated": time.strftime("%H:%M:%S"),
                        "match_type": "BR_EVO", "_pending": True,
                        "last_info": "Logging in…",
                    }
                    n += 1
        except Exception:
            pass
        return n

    def _prune_pending(self, real_uid: str = None):
        """লগইন হয়ে গেলে placeholder সরাও (guest uid ≠ real id হলেও)"""
        for k in [k for k, a in self.accounts.items() if a.get("_pending")]:
            real = self.guest_alias.get(k)
            if k == real_uid or (real and real != k and real in self.accounts
                                 and not self.accounts[real].get("_pending")):
                self.accounts.pop(k, None)

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int, likes: int = 0):
        uid_str = str(uid)
        # placeholder থাকলে আসল ডেটা দিয়ে নতুন করে রেজিস্টার হবে
        if uid_str in self.accounts and self.accounts[uid_str].get("_pending"):
            self.accounts.pop(uid_str, None)
        self._prune_pending(uid_str)
        # ✅ ব্ল্যাকলিস্টে থাকলে re-register করবে না — এটাই মূল সমস্যা ছিল
        if uid_str in self.deleted_uids:
            return
        if uid_str not in self.accounts:
            # ✅ নতুন আইডি (dashboard বা accounts.json থেকে) সবসময় AUTO মোডে শুরু হবে
            self.match_types.pop(uid_str, None)
            # ✅ FIX: নতুন আইডি এলে বাকি আইডির BR/LW সেটিং রিসেট হবে না;
            # নতুন আইডি বর্তমান global মোড (BR / LONE_WOLF) পাবে
            if self.global_mode in ("BR", "LONE_WOLF"):
                self.match_types[uid_str] = self.global_mode
            self.accounts[uid_str] = {
                "uid": uid_str,
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": level or 1,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "likes": likes or 0,
                "status": "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "match_type": (self.global_mode if self.global_mode in ("BR", "LONE_WOLF", "BR_EVO")
                               else ("BR" if (level or 1) == 2 and self.global_mode == "AUTO" else "LONE_WOLF"))
            }
        else:
            acc = self.accounts[uid_str]
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
                self.get_match_type(uid_str)   # level barhle BR -> LW auto switch
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["likes"] = likes
            acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()
        self.check_level_limit(uid_str)

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        # ✅ ডিলিট করা আইডি আপডেট হবে না
        if uid_str in self.deleted_uids:
            return
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
                self.get_match_type(uid_str)   # level barhle BR -> LW auto switch
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            acc["last_updated"] = time.strftime("%H:%M:%S")
            diff = current_exp - old_exp
            if diff > 0:
                self.log(f"Account {acc['nickname']} ({uid_str}) gained +{diff} EXP! Total: +{acc['gained_exp']}", "success", uid_str)
            self.recalc_totals()
            self.check_level_limit(uid_str)

            # ✅ AUTO-DELETE: gained_exp ≥ exp_limit হলে আইডি অটোমেটিক মুছে যাবে
            if self.exp_limit > 0 and acc["gained_exp"] >= self.exp_limit and uid_str not in self.auto_delete_queue:
                self.auto_delete_queue.add(uid_str)
                nickname = acc.get("nickname", uid_str)
                # তৎক্ষণাৎ blacklist করো — worker আর কোনো match খেলবে না
                self.deleted_uids.add(uid_str)
                self._save_deleted_uids()       # ✅ FIX: redeploy-এর পরেও blacklist টিকে থাকবে
                self.match_types.pop(uid_str, None)
                # ✅ FIX: Dashboard ও JSON থেকে সাথে সাথে (synchronously) মুছে ফেলো।
                # আগে শুধু async task-এর উপর নির্ভর করত — task fail হলে account
                # "Offline" হয়ে dashboard-এ রয়ে যেত। এখন level_limit-এর মতোই
                # synchronous removal করা হচ্ছে।
                self.accounts.pop(uid_str, None)
                self.recalc_totals()
                self._remove_from_json(uid_str, "complete")
                self.log(
                    f"[AUTO-DELETE] {nickname} ({uid_str}) → {acc['gained_exp']} EXP অর্জন করেছে "
                    f"(লিমিট: {self.exp_limit})। আইডি dashboard ও accounts.json থেকে সরিয়ে delete_accounts.json-এ রাখা হয়েছে।",
                    "warning", uid_str
                )
                # Async cleanup: এখন শুধু worker task cancel করতে হবে
                try:
                    # ✅ CRASH FIX: get_event_loop() → get_running_loop() — Python 3.12-এ safe
                    asyncio.get_running_loop().create_task(
                        self._async_auto_delete(uid_str)
                    )
                except RuntimeError:
                    self.auto_delete_queue.discard(uid_str)

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        # ✅ ডিলিট করা আইডি status update হবে না
        if uid_str in self.deleted_uids:
            return
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if status in ("ONLINE", "IN_MATCH", "SEARCHING"):
                self.accounts[uid_str].pop("last_error", None)
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def set_error(self, uid: str, message: str):
        uid_str = str(uid)
        if uid_str in self.deleted_uids:
            return
        if uid_str in self.accounts:
            self.accounts[uid_str]["last_error"] = f"{time.strftime('%H:%M:%S')} - {message}"[:300]

    def record_login_fail(self, uid: str):
        """Login failure count বাড়ায়। MAX_LOGIN_FAILS পেরোলে আইডি dashboard থেকে auto-remove হয়।"""
        uid_str = str(uid)
        if uid_str in self.deleted_uids:
            return
        self.login_fail_counts[uid_str] = self.login_fail_counts.get(uid_str, 0) + 1
        count = self.login_fail_counts[uid_str]
        self.log(
            f"[LOGIN-FAIL] UID {uid_str} → {count}/{self.MAX_LOGIN_FAILS} consecutive login failure",
            "warning", uid_str
        )
        if count >= self.MAX_LOGIN_FAILS:
            # ✅ থ্রেশহোল্ড পার হলে EXP-limit-এর মতোই synchronous removal
            nickname = (self.accounts.get(uid_str) or {}).get("nickname", uid_str)
            self.deleted_uids.add(uid_str)
            self._save_deleted_uids()
            self.match_types.pop(uid_str, None)
            self.login_fail_counts.pop(uid_str, None)
            self.accounts.pop(uid_str, None)
            self.recalc_totals()
            self._remove_from_json(uid_str, "error")
            self.log(
                f"[LOGIN-FAIL-REMOVE] {nickname} ({uid_str}) → {count} বার connection fail। "
                f"আইডি dashboard ও accounts.json থেকে সরিয়ে delete_accounts.json-এ রাখা হয়েছে।",
                "error", uid_str
            )
            try:
                asyncio.get_running_loop().create_task(self._async_login_fail_remove(uid_str))
            except RuntimeError:
                pass

    def reset_login_fail(self, uid: str):
        """সফল login-এ fail counter রিসেট করে।"""
        self.login_fail_counts.pop(str(uid), None)

    async def _async_login_fail_remove(self, uid_str: str):
        """login fail-এর কারণে removed আইডির async worker cancel।"""
        try:
            short_key = uid_str.replace("tok_", "")[:10]
            for worker_key in [uid_str, short_key]:
                if worker_key in self.account_workers:
                    task = self.account_workers.pop(worker_key)
                    task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass
        except Exception as e:
            self.log(f"[LOGIN-FAIL-REMOVE ERROR] UID {uid_str}: {e}", "error", uid_str)

    def set_info(self, uid: str, message: str):
        uid_str = str(uid)
        if uid_str in self.deleted_uids:
            return
        if uid_str in self.accounts:
            self.accounts[uid_str]["last_info"] = f"{time.strftime('%H:%M:%S')} - {message}"[:300]

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
            self.log(f"Account {self.accounts[uid_str]['nickname']} finished Match #{self.accounts[uid_str]['matches_played']}", "info", uid_str)

    def recalc_totals(self):
        # ✅ PERF FIX: 200 account-এ প্রতিবার full sum না করে একবারে গণনা
        self.total_gained_exp = sum(
            int(acc.get("gained_exp", 0) or 0) for acc in self.accounts.values()
        )


bot_state = BotState()


# ==================== HTTP HANDLERS ====================

_HTML_BYTES = None

async def handle_index(request: web.Request) -> web.Response:
    # Frontend is served from templates/index.html.
    global _HTML_BYTES
    if _HTML_BYTES is None:
        with open(DASHBOARD_TEMPLATE, "rb") as template_file:
            _HTML_BYTES = template_file.read()
    et = '"' + hashlib.md5(_HTML_BYTES).hexdigest()[:16] + '"'
    if request.headers.get("If-None-Match") == et:
        return web.Response(status=304, headers={"ETag": et, "Cache-Control": "no-cache"})
    return web.Response(body=_HTML_BYTES, content_type="text/html", charset="utf-8",
                        headers={"ETag": et, "Cache-Control": "no-cache"})


_STATS_CACHE: Dict[str, Any] = {}   # key -> (timestamp, raw_bytes, etag, gzip_bytes)
_STATS_TTL = 2.0                     # সেকেন্ড — অনেক ট্যাব/ইউজার থাকলেও সার্ভার ১ বারই বানাবে
_STATS_STALE_MAX = 90.0              # এর মধ্যে পুরনো snapshot দিয়েও সাথে সাথে reply দেওয়া হয় (পেছনে নতুন বানায়)
_LAST_STATS_REQ = 0.0
_REBUILDING: set = set()
_BG_TASKS: list = []

# ---- Event-loop lag monitor: bot-এর CPU load কতটা তা মাপে (app.py এটা দেখে login/launch ধীর-দ্রুত করে) ----
_LOOP_LAG = 0.0

def get_loop_lag() -> float:
    return _LOOP_LAG

async def _loop_lag_monitor():
    global _LOOP_LAG
    while True:
        t = time.monotonic()
        await asyncio.sleep(0.5)
        lag = max(0.0, time.monotonic() - t - 0.5)
        _LOOP_LAG = lag if lag > _LOOP_LAG else (_LOOP_LAG * 0.6 + lag * 0.4)

async def _snapshot_refresher():
    """Admin snapshot আগে থেকেই বানিয়ে রাখে — /api/stats তখন শুধু ready bytes ফেরত দেয়।"""
    while True:
        try:
            if time.monotonic() - _LAST_STATS_REQ < 120:
                await _store_snapshot(None, "admin", "admin")
        except Exception:
            pass
        await asyncio.sleep(1.5)

async def _store_snapshot(request, role: str, ckey: str):
    import gzip as _gzip
    resp = await _build_stats(request, role)
    body = resp.body if isinstance(resp.body, (bytes, bytearray)) else resp.text.encode("utf-8")
    body = bytes(body)
    etag = '"' + hashlib.md5(body).hexdigest()[:16] + '"'
    gz = _gzip.compress(body, 4) if len(body) > 1024 else None
    if len(_STATS_CACHE) > 200:
        _STATS_CACHE.clear()
    _STATS_CACHE[ckey] = (time.monotonic(), body, etag, gz)
    return _STATS_CACHE[ckey]

async def _rebuild_bg(request, role: str, ckey: str):
    try:
        await _store_snapshot(request, role, ckey)
    except Exception:
        pass
    finally:
        _REBUILDING.discard(ckey)


async def handle_get_stats(request: web.Request) -> web.Response:
    global _LAST_STATS_REQ
    role = request.get("role", "admin")
    ckey = role if role != "user" else "user:" + str(_owner_id(request))
    now = time.monotonic()
    _LAST_STATS_REQ = now
    hit = _STATS_CACHE.get(ckey)
    if hit and now - hit[0] < _STATS_TTL:
        return _stats_reply(request, hit)
    if hit and now - hit[0] < _STATS_STALE_MAX:
        # পুরনো snapshot সাথে সাথে দাও, নতুনটা পেছনে বানাও — user কখনো অপেক্ষা করবে না
        if ckey not in _REBUILDING:
            _REBUILDING.add(ckey)
            asyncio.ensure_future(_rebuild_bg(request, role, ckey))
        return _stats_reply(request, hit)
    hit = await _store_snapshot(request, role, ckey)
    return _stats_reply(request, hit)


def _stats_reply(request: web.Request, hit) -> web.Response:
    _ts, body, etag, gz = hit
    # ডেটা বদলায়নি → 304, কোনো body পাঠানো লাগে না
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    headers = {"ETag": etag, "Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
    if gz is not None and "gzip" in request.headers.get("Accept-Encoding", "").lower():
        headers["Content-Encoding"] = "gzip"   # আগে থেকেই compress করা — প্রতি request-এ CPU লাগে না
        return web.Response(body=gz, content_type="application/json", headers=headers)
    return web.Response(body=body, content_type="application/json", headers=headers)


async def handle_healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok", headers={"Cache-Control": "no-store"})


async def _build_stats(request: web.Request, role: str) -> web.Response:
    bot_state._prune_pending()
    accounts_data = list(bot_state.accounts.values())
    logs = list(bot_state.logs)[-60:]  # ✅ FIX: deque → list convert করে slice
    total_matches = bot_state.total_matches
    total_exp = bot_state.total_gained_exp
    if role == "user":
        # ✅ User শুধু নিজের যোগ করা আইডি ও সেগুলোর লগ দেখবে
        me = _owner_id(request)
        _owned: Dict[str, bool] = {}
        def _mine(k) -> bool:
            k = str(k)
            if k not in _owned:
                _owned[k] = bool(me) and bot_state.owner_of(k) == me
            return _owned[k]
        accounts_data = [a for a in accounts_data if _mine(a.get("uid"))]
        logs = [l for l in bot_state.logs if l.get("uid") and _mine(l["uid"])][-60:]
        total_matches = sum(int(a.get("matches_played", 0) or 0) for a in accounts_data)
        total_exp = sum(int(a.get("gained_exp", 0) or 0) for a in accounts_data)
    # ✅ বেশি লেভেল উপরে (descending); একই লেভেল হলে বেশি gained EXP আগে
    accounts_data.sort(key=lambda x: (int(x.get("level", 0) or 0), x.get("gained_exp", 0)), reverse=True)
    payload = {
        "total_accounts": len(accounts_data),
        "total_matches": total_matches,
        "total_gained_exp": total_exp,
        "accounts": accounts_data,
        "logs": logs,
        "uptime": int(time.time() - bot_state.start_time),
        "global_running": bot_state.global_running,
        "global_mode": bot_state.global_mode,
        "exp_limit": bot_state.exp_limit,
        "level_limit": bot_state.level_limit,
        "user_add_limit": bot_state.user_add_limit,
        "deleted_file_count": bot_state.deleted_file_count() if role != "user" else 0,
        "role": role,
        # ✅ AUTO-RESTART info
        "auto_restart_enabled": bot_state.auto_restart_enabled,
        "auto_restart_interval_hours": bot_state.auto_restart_interval_hours,
        "auto_restart_break_minutes": bot_state.auto_restart_break_minutes,
        "auto_restart_phase": bot_state._auto_restart_phase,
        "auto_restart_next_ts": bot_state._auto_restart_next_ts,
    }
    if _orjson is not None:
        return web.Response(body=_orjson.dumps(payload), content_type="application/json")
    return web.json_response(payload)


def _check_user_limit(role: str, owner: Optional[str], owner_key: str, existing: list) -> Optional[str]:
    """User-এর আইডি লিমিট পূর্ণ হলে error মেসেজ ফেরত দেয়। Admin-এর কোনো লিমিট নেই।"""
    lim = bot_state.user_add_limit
    if role != "user" or lim <= 0 or not owner:
        return None
    # নিজের আগে যোগ করা আইডি আবার যোগ করলে নতুন স্লট লাগে না
    if bot_state.account_owner.get(owner_key) == owner:
        return None
    if bot_state.count_user_ids(owner, existing) >= lim:
        return f"ID limit reached. You can add up to {lim} ID(s) only."
    return None


async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        role = request.get("role", "admin")
        new_owner_cookie = None
        owner = None
        if role == "user":
            owner = _owner_id(request)
            if not owner:
                owner = _secrets.token_hex(6)
                new_owner_cookie = _owner_cookie_value(owner)
        accounts_file = ACCOUNTS_FILE_PATH
        existing = []
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password are required"})
            owner_key = uid
            if role == "user" and (any(str(acc.get("uid")) == uid for acc in existing) or uid in bot_state.accounts) \
                    and bot_state.account_owner.get(uid) != owner:
                return web.json_response({"status": "error", "error": "This account already exists"})
            lim_err = _check_user_limit(role, owner, owner_key, existing)
            if lim_err:
                return web.json_response({"status": "error", "error": lim_err})
            existing = [acc for acc in existing if str(acc.get("uid")) != uid]
            existing.append({"uid": uid, "password": pwd})
            # ✅ Re-add করলে blacklist থেকে সরাও — না হলে আর চালু হবে না
            bot_state.deleted_uids.discard(uid)
            bot_state._save_deleted_uids()  # ✅ FIX: ফাইল থেকেও সরাও
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token is required"})
            owner_key = f"tok_{token[:10]}"
            if role == "user" and (any(acc.get("token") == token for acc in existing) or owner_key in bot_state.accounts) \
                    and bot_state.account_owner.get(owner_key) != owner:
                return web.json_response({"status": "error", "error": "This account already exists"})
            lim_err = _check_user_limit(role, owner, owner_key, existing)
            if lim_err:
                return web.json_response({"status": "error", "error": lim_err})
            existing = [acc for acc in existing if acc.get("token") != token]
            existing.append({"token": token})
            # ✅ Token re-add করলে blacklist থেকে সরাও
            bot_state.deleted_uids.discard(token[:10])
            bot_state.deleted_uids.discard(f"tok_{token[:10]}")
            bot_state._save_deleted_uids()  # ✅ FIX: ফাইল থেকেও সরাও
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        # মালিক নথিভুক্ত করো (User হলে) — Admin যোগ করলে মালিক থাকে না, শুধু Admin দেখবে
        if role == "user" and owner:
            bot_state.account_owner[owner_key] = owner
            bot_state._save_owners()
        elif role == "admin":
            if bot_state.account_owner.pop(owner_key, None) is not None:
                bot_state._save_owners()

        bot_state.log(f"New account added: {data.get('uid') or 'Token'}", "success", owner_key)

        # Trigger dynamic worker launch
        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        resp = web.json_response({"status": "ok"})
        if new_owner_cookie:
            resp.set_cookie(OWNER_COOKIE, new_owner_cookie, max_age=365 * 86400,
                            httponly=True, samesite="Lax", secure=_is_https(request), path="/")
        return resp
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "uid missing"})

        # token-based worker key: "tok_abcdefghij" → "abcdefghij"
        short_key = uid.replace("tok_", "")[:10]

        # ✅ সব accounts*.json ফাইলে খুঁজে atomic write দিয়ে delete করে
        for accounts_file in get_all_account_files_dashboard():
            if not os.path.exists(accounts_file):
                continue
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, list):
                    continue

                new_list = [
                    acc for acc in existing
                    if str(acc.get("uid", "")).strip() != uid
                    and str(acc.get("token", ""))[:10] != short_key
                ]

                if len(new_list) < len(existing):
                    # ✅ Atomic write — crash হলে ফাইল নষ্ট হবে না
                    tmp_file = accounts_file + ".tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(new_list, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_file, accounts_file)
            except Exception:
                pass

        # ✅ STEP 1: আগেই ব্ল্যাকলিস্টে যোগ করো
        # এর ফলে চলমান worker আর re-register করতে পারবে না
        bot_state.deleted_uids.add(uid)
        bot_state.deleted_uids.add(short_key)
        bot_state._save_deleted_uids()  # ✅ FIX: redeploy-এর পরেও blacklist টিকে থাকবে

        # ✅ STEP 2: bot_state থেকে সরাও এবং totals আপডেট করো
        if uid in bot_state.accounts:
            del bot_state.accounts[uid]
            bot_state.recalc_totals()

        # ✅ STEP 3: Worker বাতিল করো এবং সম্পূর্ণভাবে await করো
        # break ছিল আগে — এর ফলে দুটো key-এর একটাই cancel হতো
        # এখন দুটোই cancel করা হবে এবং properly await করা হবে
        for worker_key in [uid, short_key]:
            if worker_key in bot_state.account_workers:
                task = bot_state.account_workers.pop(worker_key)
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass  # cancel হয়েছে — এটাই স্বাভাবিক

        bot_state.log(f"Account {uid} deleted from dashboard and accounts.json.", "warning", uid)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_reload_accounts(request: web.Request) -> web.Response:
    """
    accounts*.json ফাইল থেকে নতুন করে সব account load করে।
    - deleted_uids blacklist পুরোপুরি clear হয়
    - যে accounts এখন চলছে না কিন্তু JSON এ আছে সেগুলো স্বয়ংক্রিয়ভাবে চালু হয়
    - ইতিমধ্যে চলমান accounts অপরিবর্তিত থাকে
    """
    try:
        # ✅ STEP 1: পুরো blacklist clear করো
        cleared = len(bot_state.deleted_uids)
        bot_state.deleted_uids.clear()
        bot_state.level_remove_queue.clear()
        bot_state._save_deleted_uids()  # ✅ FIX: ফাইলও clear করো

        # ✅ STEP 2: app.py-এর reload callback ডাকো
        bot_state.preload_pending()   # সাথে সাথে কার্ড দেখাও
        _STATS_CACHE.clear()
        added = 0
        pending = False
        if "on_reload_accounts" in bot_state.refresh_callbacks:
            task = asyncio.ensure_future(bot_state.refresh_callbacks["on_reload_accounts"]())
            done, _ = await asyncio.wait({task}, timeout=1.5)   # দেরি হলে ব্যাকগ্রাউন্ডে চলবে — button আটকে থাকবে না
            if task in done:
                added = task.result()
            else:
                pending = True

        msg = (f"Reload started in background ({cleared} blacklist cleared). Accounts will appear shortly."
               if pending else
               f"Reload complete: {cleared} blacklisted UIDs cleared, {added} new account(s) started.")
        bot_state.log(msg, "success")
        return web.json_response({"status": "ok", "message": msg, "cleared": cleared, "started": added})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restore_deleted(request: web.Request) -> web.Response:
    """delete_accounts.json-এর আইডি ড্যাশবোর্ডে ফিরিয়ে এনে আবার চালু করে"""
    try:
        restored = bot_state.restore_deleted_accounts()
        if restored == 0:
            return web.json_response({"status": "ok", "restored": 0,
                                      "message": "delete_accounts.json খালি — ফেরানোর মতো কোনো আইডি নেই।"})
        bot_state.preload_pending()
        _STATS_CACHE.clear()
        started, pending = 0, False
        if "on_reload_accounts" in bot_state.refresh_callbacks:
            task = asyncio.ensure_future(bot_state.refresh_callbacks["on_reload_accounts"]())
            done, _ = await asyncio.wait({task}, timeout=1.5)
            if task in done:
                started = task.result()
            else:
                pending = True
        msg = (f"{restored}টি আইডি delete_accounts.json থেকে ফিরেছে — ব্যাকগ্রাউন্ডে চালু হচ্ছে।" if pending
               else f"{restored}টি আইডি delete_accounts.json থেকে ফিরেছে, {started}টি চালু হয়েছে।")
        bot_state.log(msg, "success")
        return web.json_response({"status": "ok", "restored": restored, "started": started, "message": msg})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_set_match_type(request: web.Request) -> web.Response:
    """Dashboard থেকে UID-এর match type পরিবর্তন করা: BR, LONE_WOLF অথবা LW_HS"""
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        match_type = str(data.get("match_type", "LONE_WOLF")).strip().upper()
        if not uid:
            return web.json_response({"status": "error", "error": "UID required"}, status=400)
        if match_type not in ("BR", "LONE_WOLF", "LW_HS", "BR_EVO"):
            return web.json_response({"status": "error", "error": "Invalid match_type. Use BR, LONE_WOLF or LW_HS"}, status=400)
        bot_state.set_match_type(uid, match_type)
        bot_state.global_mode = "CUSTOM"
        label = "🐻 Bear EVO" if match_type == "BR_EVO" else ("⚔ Battle Royale" if match_type == "BR" else ("🎯 LW Headshot" if match_type == "LW_HS" else "🐺 Lone Wolf"))
        bot_state.log(f"[MATCH TYPE] UID {uid} → {label}", "info", uid)
        return web.json_response({"status": "ok", "uid": uid, "match_type": match_type})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_toggle_global(request: web.Request) -> web.Response:
    """সব আইডি ON/OFF করা — running=true হলে ম্যাচ শুরু, false হলে বন্ধ"""
    try:
        data = await request.json()
        running = bool(data.get("running", True))
        bot_state.global_running = running
        state_str = "চালু (ON)" if running else "বন্ধ (OFF)"
        bot_state.log(f"[GLOBAL] সব বট {state_str} করা হয়েছে", "success" if running else "warning")

        # If turning OFF, update all account statuses to PAUSED
        if not running:
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    status = bot_state.accounts[uid_str].get("status", "ONLINE")
                    if status not in ("OFFLINE", "ERROR", "CONNECTING"):
                        bot_state.accounts[uid_str]["status"] = "PAUSED"
        else:
            # Turning ON — reset PAUSED statuses to ONLINE
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    if bot_state.accounts[uid_str].get("status") == "PAUSED":
                        bot_state.accounts[uid_str]["status"] = "ONLINE"

        return web.json_response({"status": "ok", "running": running})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_set_all_mode(request: web.Request) -> web.Response:
    """ড্যাশবোর্ডের সব আইডির match type একসাথে পরিবর্তন করা"""
    try:
        data = await request.json()
        mode = str(data.get("mode", "LONE_WOLF")).strip().upper()
        if mode not in ("BR", "LONE_WOLF", "LW_HS", "AUTO"):
            return web.json_response({"status": "error", "error": "Invalid mode. Use BR, LONE_WOLF, LW_HS or AUTO"}, status=400)

        changed = 0
        bot_state.global_mode = mode
        if mode == "AUTO":
            # ✅ AUTO: সব আইডির manually-forced match_type সরিয়ে দেওয়া
            # get_match_type() এর Level-based auto-logic আবার কাজ করবে
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    # match_types থেকে সরালে get_match_type() নিজেই level দেখে সিদ্ধান্ত নেবে
                    bot_state.match_types.pop(uid_str, None)
                    if uid_str in bot_state.accounts:
                        lvl = bot_state.get_account_level(uid_str)
                        auto_mt = "BR" if lvl == 2 else "LONE_WOLF"
                        bot_state.accounts[uid_str]["match_type"] = auto_mt
                    changed += 1
            label = "🔄 Auto Level Mode"
        else:
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    bot_state.set_match_type(uid_str, mode)
                    changed += 1
            label = "⚔ Battle Royale" if mode == "BR" else ("🎯 LW Headshot" if mode == "LW_HS" else "🐺 Lone Wolf")

        bot_state.log(f"[GLOBAL MODE] সব {changed}টি আইডি → {label}", "success")
        return web.json_response({"status": "ok", "mode": mode, "changed": changed})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_set_exp_limit(request: web.Request) -> web.Response:
    """EXP লিমিট আপডেট করা — এই সীমা পার হলে আইডি অটো ডিলিট হবে"""
    try:
        data = await request.json()
        raw = data.get("exp_limit", None)
        if raw is None:
            return web.json_response({"status": "error", "error": "exp_limit missing"}, status=400)
        try:
            limit = int(str(raw).strip().replace(",", ""))
        except (ValueError, TypeError):
            return web.json_response({"status": "error", "error": "exp_limit must be a number"}, status=400)
        if limit < 0:
            return web.json_response({"status": "error", "error": "exp_limit cannot be negative"}, status=400)
        bot_state.exp_limit = limit
        bot_state._save_settings()  # ✅ FIX: redeploy-এর পরেও টিকে থাকবে
        msg = f"EXP লিমিট সেট: {limit:,}" if limit > 0 else "EXP লিমিট বন্ধ (0 = কোনো লিমিট নেই)"
        bot_state.log(f"[EXP LIMIT] {msg}", "success")
        return web.json_response({"status": "ok", "exp_limit": limit})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_set_level_limit(request: web.Request) -> web.Response:
    """Level লিমিট সেট — আইডি এই level-এ পৌঁছালে dashboard থেকে সরে যাবে (0 = বন্ধ)"""
    try:
        data = await request.json()
        raw = data.get("level_limit", None)
        if raw is None:
            return web.json_response({"status": "error", "error": "level_limit missing"}, status=400)
        try:
            limit = int(str(raw).strip())
        except (ValueError, TypeError):
            return web.json_response({"status": "error", "error": "level_limit must be a number"}, status=400)
        if limit == 1 or limit < 0 or limit > 200:
            return web.json_response({"status": "error", "error": "Level লিমিট 0 (বন্ধ) অথবা 2 থেকে 200 এর মধ্যে দিন"}, status=400)
        bot_state.level_limit = limit
        bot_state._save_settings()  # ✅ FIX: redeploy-এর পরেও টিকে থাকবে
        msg = f"Level লিমিট সেট: Lv{limit}" if limit > 0 else "Level লিমিট বন্ধ (0 = কোনো লিমিট নেই)"
        bot_state.log(f"[LEVEL LIMIT] {msg}", "success")
        bot_state.enforce_level_limit()
        return web.json_response({"status": "ok", "level_limit": limit})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_set_user_limit(request: web.Request) -> web.Response:
    """প্রতিটি User সর্বোচ্চ কয়টি আইডি যোগ করতে পারবে — শুধু Admin ঠিক করে (0 = সীমাহীন)"""
    try:
        data = await request.json()
        raw = data.get("user_add_limit", None)
        if raw is None:
            return web.json_response({"status": "error", "error": "user_add_limit missing"}, status=400)
        try:
            limit = int(str(raw).strip())
        except (ValueError, TypeError):
            return web.json_response({"status": "error", "error": "user_add_limit must be a number"}, status=400)
        if limit < 0 or limit > 100000:
            return web.json_response({"status": "error", "error": "user_add_limit must be 0 to 100000"}, status=400)
        bot_state.user_add_limit = limit
        bot_state._save_settings()
        msg = f"প্রতি User সর্বোচ্চ {limit}টি আইডি" if limit > 0 else "User ID লিমিট বন্ধ (0 = সীমাহীন)"
        bot_state.log(f"[USER LIMIT] {msg}", "success")
        return web.json_response({"status": "ok", "user_add_limit": limit})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


async def handle_set_auto_restart(request: web.Request) -> web.Response:
    """Auto-Restart সেটিং আপডেট — enabled/disabled + interval + break"""
    try:
        data = await request.json()
        enabled = bool(data.get("enabled", bot_state.auto_restart_enabled))
        interval_h = float(data.get("interval_hours", bot_state.auto_restart_interval_hours) or 1.5)
        break_m = int(data.get("break_minutes", bot_state.auto_restart_break_minutes) or 10)
        interval_h = max(0.5, min(24, interval_h))
        break_m = max(1, min(60, break_m))

        was_enabled = bot_state.auto_restart_enabled
        bot_state.auto_restart_enabled = enabled
        bot_state.auto_restart_interval_hours = interval_h
        bot_state.auto_restart_break_minutes = break_m
        bot_state._save_settings()

        if enabled and not was_enabled:
            # নতুন করে চালু হলে timer রিসেট করে task শুরু
            bot_state._auto_restart_phase = "running"
            bot_state._auto_restart_next_ts = time.time() + interval_h * 3600
            _start_auto_restart_task()
            bot_state.log(
                f"[AUTO-RESTART] চালু — প্রতি {interval_h}h পর {break_m}min বিরতি",
                "success"
            )
        elif not enabled and was_enabled:
            _stop_auto_restart_task()
            bot_state._auto_restart_phase = ""
            bot_state._auto_restart_next_ts = 0.0
            bot_state.log("[AUTO-RESTART] বন্ধ করা হয়েছে", "warning")
        elif enabled and was_enabled:
            # সেটিং আপডেট — task restart করে নতুন interval দিয়ে
            _stop_auto_restart_task()
            bot_state._auto_restart_phase = "running"
            bot_state._auto_restart_next_ts = time.time() + interval_h * 3600
            _start_auto_restart_task()
            bot_state.log(
                f"[AUTO-RESTART] আপডেট — প্রতি {interval_h}h পর {break_m}min বিরতি",
                "info"
            )

        return web.json_response({
            "status": "ok",
            "enabled": enabled,
            "interval_hours": interval_h,
            "break_minutes": break_m,
        })
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)}, status=500)


def _start_auto_restart_task():
    """Auto-restart background task শুরু করে"""
    _stop_auto_restart_task()
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_auto_restart_loop())
        bot_state._auto_restart_task = task
        _BG_TASKS.append(task)
    except RuntimeError:
        pass


def _stop_auto_restart_task():
    """Auto-restart background task বন্ধ করে"""
    task = bot_state._auto_restart_task
    if task and not task.done():
        task.cancel()
    bot_state._auto_restart_task = None


async def _auto_restart_loop():
    """
    Auto-Restart মূল loop:
    1. interval_hours পর্যন্ত অপেক্ষা
    2. সব account OFFLINE → ১০ মিনিট বিরতি
    3. global_running=True → সব reconnect → stats reset
    4. আবার শুরু
    """
    try:
        while bot_state.auto_restart_enabled:
            # ─── Phase 1: RUNNING ─── interval শেষ হওয়ার অপেক্ষা
            bot_state._auto_restart_phase = "running"
            wait_sec = bot_state._auto_restart_next_ts - time.time()
            if wait_sec > 0:
                await asyncio.sleep(wait_sec)
            if not bot_state.auto_restart_enabled:
                break

            # ─── Phase 2: BREAK শুরু ─── সব account offline
            break_min = bot_state.auto_restart_break_minutes
            bot_state._auto_restart_phase = "break"
            bot_state._auto_restart_next_ts = time.time() + break_min * 60
            bot_state.log(
                f"[AUTO-RESTART] 🔴 সব account offline করা হচ্ছে — {break_min} মিনিট বিরতি",
                "warning"
            )

            # ✅ global_running বন্ধ → সব account game থেকে LOGOUT
            bot_state.global_running = False
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    status_now = bot_state.accounts[uid_str].get("status", "ONLINE")
                    if status_now not in ("OFFLINE", "ERROR"):
                        bot_state.accounts[uid_str]["status"] = "OFFLINE"
                        bot_state.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")
                        # ✅ JWT token clear → fresh login forced
                        bot_state.accounts[uid_str]["token"] = ""
                        bot_state.accounts[uid_str]["jwt"] = ""

            # ✅ on_reload_accounts call → app.py সব account disconnect করবে
            if "on_reload_accounts" in bot_state.refresh_callbacks:
                try:
                    await asyncio.sleep(2)  # disconnect হতে 2 সেকেন্ড দাও
                    bot_state.log("[AUTO-RESTART] 🔴 Game থেকে সব ID logout হয়েছে", "warning")
                except Exception as e:
                    bot_state.log(f"[AUTO-RESTART] Logout error: {e}", "error")

            # ─── Phase 3: বিরতি শেষে reconnect ───
            await asyncio.sleep(break_min * 60)
            if not bot_state.auto_restart_enabled:
                break

            bot_state._auto_restart_phase = "reconnecting"
            bot_state.log(
                "[AUTO-RESTART] 🟢 বিরতি শেষ — সব ID fresh login হচ্ছে",
                "success"
            )

            # ─── Stats রিসেট ───
            bot_state.total_matches = 0
            bot_state.total_gained_exp = 0
            bot_state.start_time = time.time()
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    acc = bot_state.accounts[uid_str]
                    cur_exp = acc.get("current_exp") or acc.get("exp") or acc.get("initial_exp") or 0
                    acc["initial_exp"] = cur_exp
                    acc["gained_exp"] = 0
                    acc["matches_played"] = 0
                    acc["status"] = "CONNECTING"
                    acc["last_updated"] = time.strftime("%H:%M:%S")

            # ✅ global_running চালু → on_reload_accounts দিয়ে fresh re-login
            bot_state.global_running = True
            if "on_reload_accounts" in bot_state.refresh_callbacks:
                try:
                    await asyncio.ensure_future(
                        bot_state.refresh_callbacks["on_reload_accounts"]()
                    )
                    bot_state.log("[AUTO-RESTART] ✅ সব ID game-এ fresh login হয়েছে", "success")
                except Exception as e:
                    bot_state.log(f"[AUTO-RESTART] Re-login error: {e}", "error")

            # ─── Phase 4: পরবর্তী cycle সেট ───
            interval_h = bot_state.auto_restart_interval_hours
            bot_state._auto_restart_phase = "running"
            bot_state._auto_restart_next_ts = time.time() + interval_h * 3600
            bot_state.log(
                f"[AUTO-RESTART] ✅ পরবর্তী restart {interval_h} ঘন্টা পর",
                "info"
            )

    except asyncio.CancelledError:
        pass
    except Exception as e:
        bot_state.log(f"[AUTO-RESTART ERROR] {e}", "error")
    finally:
        # ✅ SAFETY: break phase-এ cancel হলে global_running পুনরুদ্ধার করা
        # যেন বট চিরতরে offline না থাকে
        if bot_state._auto_restart_phase == "break":
            bot_state.global_running = True
            for uid_str in list(bot_state.accounts.keys()):
                if uid_str not in bot_state.deleted_uids:
                    if bot_state.accounts[uid_str].get("status") == "OFFLINE":
                        bot_state.accounts[uid_str]["status"] = "CONNECTING"
            bot_state.log("[AUTO-RESTART] Task বন্ধ — সব account পুনরায় চালু", "info")
        bot_state._auto_restart_phase = ""
        if bot_state._auto_restart_task is not None:
            bot_state._auto_restart_task = None


async def handle_clear_logs(request: web.Request) -> web.Response:
    """Activity Log পরিষ্কার করা"""
    bot_state.logs.clear()
    return web.json_response({"status": "ok"})


async def start_web_dashboard(host: str = "0.0.0.0", port: int = 5000):
    try:
        bot_state.preload_pending()
    except Exception:
        pass
    app = web.Application(middlewares=[compress_middleware])
    app.router.add_get("/healthz", handle_healthz)
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/accounts/reload", handle_reload_accounts)
    app.router.add_post("/api/accounts/restore-deleted", handle_restore_deleted)
    app.router.add_post("/api/account/match-type", handle_set_match_type)
    app.router.add_post("/api/bot/toggle", handle_toggle_global)
    app.router.add_post("/api/accounts/set-all-mode", handle_set_all_mode)
    app.router.add_post("/api/settings/exp-limit", handle_set_exp_limit)
    app.router.add_post("/api/settings/level-limit", handle_set_level_limit)
    app.router.add_post("/api/settings/user-limit", handle_set_user_limit)
    app.router.add_post("/api/settings/auto-restart", handle_set_auto_restart)
    app.router.add_post("/api/logs/clear", handle_clear_logs)

    runner = web.AppRunner(app, access_log=None)   # প্রতি request-এর log print বন্ধ — CPU/log flood কমে
    await runner.setup()
    site = web.TCPSite(runner, host, port, backlog=1024)
    await site.start()
    _BG_TASKS.append(asyncio.ensure_future(_loop_lag_monitor()))
    _BG_TASKS.append(asyncio.ensure_future(_snapshot_refresher()))
    # ✅ AUTO-RESTART: settings লোড হয়ে থাকলে সাথে সাথে শুরু
    if bot_state.auto_restart_enabled:
        bot_state._auto_restart_phase = "running"
        # redeploy-এর পর interval থেকে নতুন করে শুরু
        bot_state._auto_restart_next_ts = time.time() + bot_state.auto_restart_interval_hours * 3600
        _start_auto_restart_task()
        bot_state.log(
            f"[AUTO-RESTART] বট চালু — প্রতি {bot_state.auto_restart_interval_hours}h পর "
            f"{bot_state.auto_restart_break_minutes}min বিরতি দিয়ে restart হবে",
            "info"
        )
    print(f"\033[92m[+] Web Dashboard running on http://localhost:{port}\033[0m")
