# portal_app.py
# FastAPI portal: Supabase'dagi captured_messages ni chiroyli UI bilan ko'rsatadi
# + (ixtiyoriy) Web Telegram orqali HAQIQIY screenshot (Playwright bilan)
# + portal ichida "ko'k link" bosilganda klient lichkasiga o'tib ketishini o'chirib qo'yadi (default)

import os
import io
import html
import textwrap
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from supabase import create_client, Client as SupabaseClient

# (ixtiyoriy) agar PIL bilan DB-textdan screenshot ham kerak bo'lsa
from PIL import Image, ImageDraw, ImageFont  # pip install pillow

load_dotenv()

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_KEY") or "").strip()

# Telegram screenshot sozlamalari (Playwright)
ENABLE_TG_SCREENSHOT = (os.getenv("ENABLE_TG_SCREENSHOT") or "1").strip() == "1"
TG_SESSION_DIR = (os.getenv("TG_SESSION_DIR") or "tg_session").strip()
TG_CACHE_DIR = (os.getenv("TG_CACHE_DIR") or "tg_cache").strip()
TG_SHOT_FULL_PAGE = (os.getenv("TG_SHOT_FULL_PAGE") or "1").strip() == "1"

# Portalda ko'k linklarni ko'rsatish / yashirish
# Default: OFF (linklar ko'rinmaydi)
SHOW_TELEGRAM_LINKS = (os.getenv("SHOW_TELEGRAM_LINKS") or "0").strip() == "1"

app = FastAPI(title="Userbot Portal")
supabase: SupabaseClient | None = None


def get_supabase() -> SupabaseClient:
    global supabase
    if supabase is not None:
        return supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL yoki SUPABASE_SERVICE_KEY topilmadi (.env ni tekshir)")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def load_row(cap_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("captured_messages").select("*").eq("id", cap_id).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Bu ID bo‘yicha xabar topilmadi (DBga yozilmagan bo‘lishi mumkin).",
        )
    return row


CSS = """
<style>
:root{
  --bg:#0b0f14;
  --panel:#121826;
  --panel2:#0f1522;
  --text:#e7eefc;
  --muted:#9fb0c8;
  --line:rgba(255,255,255,.08);
  --brand:#6aa9ff;
  --ok:#26d07c;
  --shadow: 0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  background: radial-gradient(1200px 600px at 10% 0%, rgba(106,169,255,.18), transparent 55%),
              radial-gradient(900px 500px at 90% 10%, rgba(38,208,124,.12), transparent 55%),
              var(--bg);
  color:var(--text);
}
a{color:var(--brand); text-decoration:none}
a:hover{text-decoration:underline}
.container{
  max-width:980px;
  margin:0 auto;
  padding:22px 16px 40px;
}
.topbar{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:16px;
}
.brand{
  display:flex; align-items:center; gap:10px;
}
.logo{
  width:38px; height:38px; border-radius:12px;
  background: linear-gradient(135deg, rgba(106,169,255,.9), rgba(38,208,124,.7));
  box-shadow: var(--shadow);
}
.hgroup h1{font-size:18px; margin:0; letter-spacing:.2px}
.hgroup p{margin:2px 0 0; color:var(--muted); font-size:13px}
.chip{
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 10px;
  border:1px solid var(--line);
  background:rgba(255,255,255,.03);
  border-radius:999px;
  color:var(--muted);
  font-size:12px;
}
.grid{
  display:grid;
  grid-template-columns: 1.1fr .9fr;
  gap:14px;
}
@media (max-width: 860px){
  .grid{grid-template-columns:1fr}
}
.card{
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
  border:1px solid var(--line);
  border-radius:16px;
  box-shadow: var(--shadow);
  overflow:hidden;
}
.card .hd{
  padding:12px 14px;
  border-bottom:1px solid var(--line);
  display:flex; align-items:center; justify-content:space-between; gap:10px;
  background: rgba(255,255,255,.02);
}
.card .hd .title{
  font-weight:700;
  letter-spacing:.2px;
  font-size:14px;
}
.badge{
  display:inline-flex; align-items:center;
  padding:6px 10px;
  border-radius:999px;
  font-size:12px;
  border:1px solid var(--line);
  background: rgba(255,255,255,.03);
  color:var(--muted);
}
.badge.ok{ color: rgba(38,208,124,.95); border-color: rgba(38,208,124,.25); background: rgba(38,208,124,.08);}
.card .bd{ padding:14px; }
.kv{
  display:grid;
  grid-template-columns: 140px 1fr;
  gap:10px;
  padding:10px 0;
  border-bottom:1px dashed rgba(255,255,255,.08);
}
.kv:last-child{border-bottom:none}
.k{color:var(--muted); font-size:12px}
.v{font-size:13px}
.mono{font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace}
.msg{
  white-space:pre-wrap;
  line-height:1.55;
  font-size:14px;
  color: #eaf2ff;
}
.actions{
  display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;
}
.btn{
  display:inline-flex; align-items:center; gap:8px;
  padding:9px 12px;
  border-radius:12px;
  border:1px solid var(--line);
  background: rgba(255,255,255,.03);
  color:var(--text);
  font-size:13px;
  cursor:pointer;
}
.btn:hover{ background: rgba(255,255,255,.06); }
.small{
  color:var(--muted);
  font-size:12px;
  margin-top:14px;
}
.list{
  margin:0; padding-left:18px;
}
.list li{margin:6px 0; word-break:break-word}
.preview{
  width:100%;
  border-radius:14px;
  border:1px solid var(--line);
  background: rgba(0,0,0,.25);
  display:block;
}
.note{
  padding:10px 12px;
  border:1px solid var(--line);
  border-radius:14px;
  background: rgba(255,255,255,.03);
  color: var(--muted);
  font-size:12px;
  line-height:1.45;
}
</style>
"""


def page(title: str, body: str) -> str:
    return f"""
    <html>
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>{esc(title)}</title>
        {CSS}
      </head>
      <body>
        <div class="container">
          {body}
        </div>
      </body>
    </html>
    """


# ----------------------------
#  DB TEXT -> PNG (Pillow)
# ----------------------------
def pick_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def make_db_text_screenshot_png(row: dict) -> bytes:
    W = 1080
    pad = 48
    bg = (11, 15, 20)
    panel = (18, 24, 38)
    line = (40, 52, 74)
    text = (231, 238, 252)
    muted = (159, 176, 200)
    brand = (106, 169, 255)

    title_font = pick_font(44)
    h_font = pick_font(30)
    b_font = pick_font(28)
    mono_font = pick_font(26)

    meta_lines = [
        f"Phone: {row.get('phone_number')}",
        f"Group: {row.get('group_name')} ({row.get('group_id')})",
        f"Message ID: {row.get('message_id')}",
        f"Keyword: {row.get('keyword')}",
        f"Created: {row.get('created_at')}",
        f"Sender: {row.get('sender_name')}",
    ]
    body_text = row.get("text") or ""

    wrap_width = 56
    wrapped_meta = []
    for ln in meta_lines:
        wrapped_meta += textwrap.wrap(str(ln), width=wrap_width) or [""]

    wrapped_body = []
    for ln in str(body_text).splitlines() or [""]:
        wrapped_body += textwrap.wrap(ln, width=wrap_width) or [""]
    if not wrapped_body:
        wrapped_body = [""]

    line_h = 40
    meta_h = (len(wrapped_meta) + 1) * line_h
    body_h = (len(wrapped_body) + 2) * line_h

    H = pad + 90 + 26 + meta_h + 18 + body_h + pad
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    d.text((pad, pad), "📩", font=title_font, fill=brand)
    d.text((pad + 70, pad + 4), "Captured Message", font=title_font, fill=text)

    y = pad + 90
    card_x1, card_y1 = pad, y
    card_x2, card_y2 = W - pad, y + meta_h + 20
    d.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=22, fill=panel, outline=line, width=2)

    yy = card_y1 + 18
    for ln in wrapped_meta:
        d.text((card_x1 + 18, yy), ln, font=b_font, fill=muted)
        yy += line_h

    y = card_y2 + 18
    bx1, by1 = pad, y
    bx2, by2 = W - pad, y + body_h
    d.rounded_rectangle([bx1, by1, bx2, by2], radius=22, fill=panel, outline=line, width=2)

    yy = by1 + 18
    d.text((bx1 + 18, yy), "Text:", font=h_font, fill=brand)
    yy += line_h + 8

    for ln in wrapped_body[:220]:
        d.text((bx1 + 18, yy), ln, font=mono_font, fill=text)
        yy += line_h

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ----------------------------
#  Telegram REAL Screenshot (Playwright)
# ----------------------------
def take_telegram_screenshot(message_link: str, out_path: str) -> None:
    """
    Web Telegram orqali screenshot.
    Ishlashi uchun:
      - pip install playwright
      - playwright install
      - 1 marta login qilib session saqlash (TG_SESSION_DIR)
    """
    if not ENABLE_TG_SCREENSHOT:
        raise RuntimeError("ENABLE_TG_SCREENSHOT=0 (o‘chirilgan)")

    try:
        from playwright.sync_api import sync_playwright  # noqa
    except Exception as e:
        raise RuntimeError("Playwright topilmadi: pip install playwright") from e

    os.makedirs(TG_SESSION_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            TG_SESSION_DIR,
            headless=True,
        )
        page = ctx.new_page()
        page.goto(message_link, wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=out_path, full_page=TG_SHOT_FULL_PAGE)
        ctx.close()


@app.get("/", response_class=HTMLResponse)
def home():
    body = f"""
    <div class="topbar">
      <div class="brand">
        <div class="logo"></div>
        <div class="hgroup">
          <h1>Userbot Portal</h1>
          <p>Captured xabarlarni ko‘rish paneli</p>
        </div>
      </div>
      <div class="chip">Status: <span style="color:var(--ok);font-weight:700">ONLINE</span></div>
    </div>

    <div class="card">
      <div class="hd">
        <div class="title">✅ Portal ishlayapti</div>
        <span class="badge ok">READY</span>
      </div>
      <div class="bd">
        <div class="note">
          Test uchun: <span class="mono">/m/&lt;uuid&gt;</span><br/>
          DB text-screenshot: <span class="mono">/m/&lt;uuid&gt;/shot.png</span><br/>
          Telegram real-screenshot: <span class="mono">/m/&lt;uuid&gt;/tgshot.png</span> (ENABLE_TG_SCREENSHOT=1 bo‘lsa)
        </div>

        <p class="mono" style="margin:12px 0 0;opacity:.9">Masalan: /m/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</p>
      </div>
    </div>
    """
    return page("Userbot Portal", body)


@app.get("/m/{cap_id}/shot.png")
def db_text_screenshot(cap_id: str):
    row = load_row(cap_id)
    png = make_db_text_screenshot_png(row)
    return StreamingResponse(io.BytesIO(png), media_type="image/png")


@app.get("/m/{cap_id}/tgshot.png")
def telegram_screenshot(cap_id: str):
    """
    Telegramning o'zidan screenshot (Web Telegram).
    DB'da message_link bo'lishi kerak.
    """
    row = load_row(cap_id)
    link = (row.get("message_link") or "").strip()
    if not link:
        raise HTTPException(400, "message_link yo‘q (DBga Telegram link yozilmagan).")

    os.makedirs(TG_CACHE_DIR, exist_ok=True)
    out_path = os.path.join(TG_CACHE_DIR, f"{cap_id}.png")

    # cache: avval olingan bo'lsa qayta qilmaydi
    if not os.path.exists(out_path):
        try:
            take_telegram_screenshot(link, out_path)
        except Exception as e:
            raise HTTPException(
                500,
                "Telegram screenshot xatosi. "
                "Playwright o‘rnatilganini, `playwright install` qilinganini "
                "va TG_SESSION_DIR ichida login session borligini tekshir.\n"
                f"Error: {str(e)}",
            )

    return FileResponse(out_path, media_type="image/png")


@app.get("/m/{cap_id}", response_class=HTMLResponse)
def view_message(cap_id: str):
    try:
        row = load_row(cap_id)

        urls = row.get("urls") or []
        if isinstance(urls, str):
            urls = [urls]

        msg_link = (row.get("message_link") or "").strip()
        sender_link = (row.get("sender_link") or "").strip()

        # Linklar: default OFF (klent lichkasiga o'tib ketmasin)
        links_block = ""
        if SHOW_TELEGRAM_LINKS:
            links = []
            if sender_link:
                links.append(f'<a class="btn" href="{esc(sender_link)}" target="_blank">👤 Sender link</a>')
            if msg_link:
                links.append(f'<a class="btn" href="{esc(msg_link)}" target="_blank">🔗 Telegram message link</a>')
            if links:
                links_block = "\n".join(links)

        # URL list (xohlasang ham o'chirib qo'yish mumkin)
        url_html = ""
        if urls:
            items = []
            for u in urls[:20]:
                u = str(u)
                # bu yerda ham link bo'lib qoladi. Agar butunlay link bo'lmasin desang:
                # items.append(f"<li class='mono'>{esc(u)}</li>")
                items.append(f'<li><a href="{esc(u)}" target="_blank">{esc(u)}</a></li>')
            url_html = (
                "<div class='card' style='margin-top:14px'>"
                "<div class='hd'><div class='title'>🔗 Linklar</div>"
                f"<span class='badge'>top {len(urls)}</span></div>"
                f"<div class='bd'><ul class='list'>{''.join(items)}</ul></div></div>"
            )

        # Telegram screenshot preview
        tg_preview = ""
        if msg_link:
            tg_preview = f"""
            <div class="card">
              <div class="hd">
                <div class="title">📸 Telegram skrinshot</div>
                <span class="badge">real</span>
              </div>
              <div class="bd">
                <img class="preview" src="/m/{esc(cap_id)}/tgshot.png" alt="telegram screenshot"/>
                <div class="small">
                  Agar bu joy error bersa: Playwright + session login kerak.
                </div>
              </div>
            </div>
            """
        else:
            tg_preview = f"""
            <div class="card">
              <div class="hd">
                <div class="title">📸 Telegram skrinshot</div>
                <span class="badge">real</span>
              </div>
              <div class="bd">
                <div class="note">
                  DB'da <span class="mono">message_link</span> yo‘q. Telegram screenshot ishlashi uchun
                  userbot DBga xabar linkini yozib qo‘yishi kerak.
                </div>
              </div>
            </div>
            """

        body = f"""
        <div class="topbar">
          <div class="brand">
            <div class="logo"></div>
            <div class="hgroup">
              <h1>Captured Message</h1>
              <p class="mono">{esc(cap_id)}</p>
            </div>
          </div>
          <div class="chip">DB: <span style="color:var(--ok);font-weight:700">Supabase</span></div>
        </div>

        <div class="grid">
          <div class="card">
            <div class="hd">
              <div class="title">🧾 Ma’lumotlar</div>
              <span class="badge ok">OK</span>
            </div>
            <div class="bd">
              <div class="kv"><div class="k">📱 Phone</div><div class="v mono">{esc(row.get("phone_number"))}</div></div>
              <div class="kv"><div class="k">👥 Group</div><div class="v">{esc(row.get("group_name"))} <span class="mono" style="opacity:.8">({esc(row.get("group_id"))})</span></div></div>
              <div class="kv"><div class="k">🆔 Message ID</div><div class="v mono">{esc(row.get("message_id"))}</div></div>
              <div class="kv"><div class="k">🔎 Keyword</div><div class="v">{esc(row.get("keyword"))}</div></div>
              <div class="kv"><div class="k">⏱ Created</div><div class="v mono">{esc(row.get("created_at"))}</div></div>

              <div class="actions">
                <a class="btn" href="/m/{esc(cap_id)}/shot.png" target="_blank">🖼️ DB Text Shot</a>
                <a class="btn" href="/m/{esc(cap_id)}/tgshot.png" target="_blank">📸 Telegram Shot</a>
                <a class="btn" href="/">🏠 Home</a>
                {links_block}
              </div>

              <div class="small">
                Linklar default o‘chirilgan: <span class="mono">SHOW_TELEGRAM_LINKS=0</span>.
                Shunda “ko‘k link” bosib klient lichkasiga ketib qolmaydi.
              </div>
            </div>
          </div>

          {tg_preview}
        </div>

        <div class="card" style="margin-top:14px">
          <div class="hd">
            <div class="title">💬 Xabar matni</div>
            <span class="badge mono">{esc(len((row.get("text") or "")))} chars</span>
          </div>
          <div class="bd">
            <div class="kv"><div class="k">👤 Sender</div><div class="v">{esc(row.get("sender_name"))}</div></div>
            <div class="msg">{esc(row.get("text") or "")}</div>
          </div>
        </div>

        {url_html}
        """
        return page(f"Message {cap_id}", body)

    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            f"<pre style='background:#111;color:#f88;padding:16px'>Internal Server Error:\\n{esc(e)}</pre>",
            status_code=500,
        )
