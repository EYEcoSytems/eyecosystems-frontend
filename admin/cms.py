#!/usr/bin/env python3
"""
Eyecosystems Lightweight CMS
Zero-dependency admin panel (Python stdlib only).
Run:  python3 admin/cms.py
Open:  http://localhost:4000/admin
Login: admin / eyeco2027 (change in config below)
"""

import http.server, json, os, re, hashlib, secrets, html, urllib.parse, mimetypes
from http.cookies import SimpleCookie
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
PORT = 4000
SITE_ROOT = Path(__file__).resolve().parent.parent
ADMIN_USER = "admin"
ADMIN_PASS_HASH = hashlib.sha256("eyeco2027".encode()).hexdigest()
SESSION_HOURS = 8

# Pages the CMS can edit
PAGES = {
    "home":         {"file": "index.html",              "label": "Home"},
    "about":        {"file": "about/index.html",        "label": "About"},
    "our-data":     {"file": "our-data/index.html",     "label": "Our Data"},
    "docs":         {"file": "docs/index.html",         "label": "Docs"},
    "contact":      {"file": "contact/index.html",      "label": "Contact"},
    "book-demo":    {"file": "book-demo/index.html",    "label": "Book a Demo"},
    "blog":         {"file": "blog/index.html",         "label": "Blog Listing"},
    "privacy":      {"file": "privacy/index.html",      "label": "Privacy Policy"},
    "terms":        {"file": "terms/index.html",        "label": "Terms of Service"},
    "accessibility":{"file": "accessibility-policy/index.html", "label": "Accessibility"},
}

# ── Sessions ────────────────────────────────────────────────────────────────
sessions = {}

def new_session():
    tok = secrets.token_hex(32)
    sessions[tok] = datetime.now() + timedelta(hours=SESSION_HOURS)
    return tok

def valid_session(tok):
    if tok and tok in sessions and sessions[tok] > datetime.now():
        return True
    sessions.pop(tok, None)
    return False

# ── HTML extractor helpers ──────────────────────────────────────────────────
def extract_editable_regions(page_html):
    """Pull text content from key regions: h1, h2, p with specific classes, etc."""
    regions = []
    patterns = [
        (r'<title>(.*?)</title>', 'title', 'Page Title'),
        (r'<meta\s+name="description"\s+content="(.*?)"', 'meta_desc', 'Meta Description'),
        (r'<h1[^>]*>(.*?)</h1>', 'h1', 'Main Heading (H1)'),
        (r'<h2[^>]*class="[^"]*deadline-h2[^"]*"[^>]*>(.*?)</h2>', 'deadline_h2', 'Deadline Heading'),
    ]
    for pat, key, label in patterns:
        m = re.search(pat, page_html, re.DOTALL)
        if m:
            val = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            val = html.unescape(val)
            regions.append({"key": key, "label": label, "value": val, "raw": m.group(0)})

    # Extract all h2s
    for i, m in enumerate(re.finditer(r'<h2[^>]*>(.*?)</h2>', page_html, re.DOTALL)):
        val = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
        val = html.unescape(val)
        if len(val) > 3 and val not in [r["value"] for r in regions]:
            regions.append({"key": f"h2_{i}", "label": f"Section Heading: {val[:50]}", "value": val, "raw": m.group(0)})

    # Extract paragraphs with known classes
    for cls_name, label_prefix in [
        ("hero-subtitle", "Hero Subtitle"),
        ("page-subtitle", "Page Subtitle"),
        ("deadline-text", "Deadline Text"),
        ("section-body", "Section Body"),
        ("footer-tagline", "Footer Tagline"),
    ]:
        for i, m in enumerate(re.finditer(rf'<p[^>]*class="[^"]*{cls_name}[^"]*"[^>]*>(.*?)</p>', page_html, re.DOTALL)):
            val = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            val = html.unescape(val)
            regions.append({"key": f"{cls_name}_{i}", "label": f"{label_prefix}", "value": val, "raw": m.group(0)})

    return regions

def apply_text_edit(page_html, old_raw, old_value, new_value):
    """Replace text inside an HTML tag without touching the markup."""
    new_raw = old_raw.replace(html.escape(old_value), html.escape(new_value))
    new_raw = new_raw.replace(old_value, new_value)
    return page_html.replace(old_raw, new_raw, 1)

# ── Admin UI HTML ───────────────────────────────────────────────────────────
def login_page(error=""):
    err_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eyecosystems CMS — Login</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0f172a;display:flex;align-items:center;justify-content:center;min-height:100vh;color:#e2e8f0}}
.login-card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:48px 40px;width:100%;max-width:400px;box-shadow:0 25px 50px rgba(0,0,0,.3)}}
.login-card h1{{font-size:24px;font-weight:700;margin-bottom:6px}}
.login-card .sub{{font-size:14px;color:#94a3b8;margin-bottom:32px}}
label{{display:block;font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}}
input{{width:100%;padding:12px 14px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:15px;margin-bottom:20px;outline:none;transition:border .15s}}
input:focus{{border-color:#00f5d0}}
button{{width:100%;padding:14px;background:#01a39e;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:background .15s}}
button:hover{{background:#019289}}
.error{{background:#7f1d1d;color:#fca5a5;padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:20px}}
.logo{{display:flex;align-items:center;gap:10px;margin-bottom:24px}}
.logo img{{height:32px}}
</style></head><body>
<div class="login-card">
<div class="logo"><img src="https://pub-629428d185ca4960a0a73c850d32294b.r2.dev/company_61718/images/44fcd4c3-2756-4f76-91cd-ed604729d4d9.png" alt="Logo"><span style="font-weight:700;font-size:18px">Eyecosystems</span></div>
<h1>Content Manager</h1>
<p class="sub">Sign in to edit your website</p>
{err_html}
<form method="POST" action="/admin/login">
<label for="u">Username</label><input id="u" name="username" type="text" autocomplete="username" required>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign In</button>
</form></div></body></html>'''

def dashboard_page():
    cards = ""
    for slug, info in PAGES.items():
        fpath = SITE_ROOT / info["file"]
        modified = datetime.fromtimestamp(fpath.stat().st_mtime).strftime("%b %d, %Y %I:%M %p") if fpath.exists() else "—"
        cards += f'''<a href="/admin/edit/{slug}" class="card">
            <div class="card-label">{html.escape(info["label"])}</div>
            <div class="card-path">/{html.escape(info["file"])}</div>
            <div class="card-mod">Last modified: {modified}</div>
        </a>'''

    # Find blog posts
    blog_dir = SITE_ROOT / "blog"
    blog_posts = ""
    if blog_dir.exists():
        for d in sorted(blog_dir.iterdir()):
            if d.is_dir() and (d / "index.html").exists() and d.name != "images":
                modified = datetime.fromtimestamp((d / "index.html").stat().st_mtime).strftime("%b %d, %Y %I:%M %p")
                blog_posts += f'''<a href="/admin/edit-post/{d.name}" class="card">
                    <div class="card-label">{html.escape(d.name.replace("-", " ").title())}</div>
                    <div class="card-path">/blog/{html.escape(d.name)}/</div>
                    <div class="card-mod">Last modified: {modified}</div>
                </a>'''

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eyecosystems CMS</title>
{ADMIN_CSS}
</head><body>
<header class="admin-header">
    <div class="admin-header-inner">
        <div class="admin-logo"><img src="https://pub-629428d185ca4960a0a73c850d32294b.r2.dev/company_61718/images/44fcd4c3-2756-4f76-91cd-ed604729d4d9.png" alt="Logo" height="28"> <span>Eyecosystems CMS</span></div>
        <div class="admin-header-right">
            <a href="/" target="_blank" class="btn-view">View Site</a>
            <a href="/admin/logout" class="btn-logout">Logout</a>
        </div>
    </div>
</header>
<main class="admin-main">
    <h1>Pages</h1>
    <p class="admin-desc">Click a page to edit its text content. Changes are saved directly to the HTML files.</p>
    <div class="card-grid">{cards}</div>

    <h1 style="margin-top:48px">Blog Posts</h1>
    <div class="card-grid">{blog_posts if blog_posts else '<p class="admin-desc">No blog posts found.</p>'}</div>
</main>
</body></html>'''

def edit_page(slug, info, success="", error=""):
    fpath = SITE_ROOT / info["file"]
    if not fpath.exists():
        return "<h1>Page not found</h1>"
    page_html = fpath.read_text()
    regions = extract_editable_regions(page_html)

    fields = ""
    for r in regions:
        esc_val = html.escape(r["value"])
        esc_raw = html.escape(r["raw"])
        is_long = len(r["value"]) > 100
        if is_long:
            fields += f'''<div class="field">
                <label>{html.escape(r["label"])}</label>
                <textarea name="val__{r["key"]}" rows="4">{esc_val}</textarea>
                <input type="hidden" name="raw__{r["key"]}" value="{esc_raw}">
                <input type="hidden" name="old__{r["key"]}" value="{esc_val}">
            </div>'''
        else:
            fields += f'''<div class="field">
                <label>{html.escape(r["label"])}</label>
                <input type="text" name="val__{r["key"]}" value="{esc_val}">
                <input type="hidden" name="raw__{r["key"]}" value="{esc_raw}">
                <input type="hidden" name="old__{r["key"]}" value="{esc_val}">
            </div>'''

    msg = ""
    if success:
        msg = '<div class="msg success">Changes saved successfully.</div>'
    if error:
        msg = f'<div class="msg error">{html.escape(error)}</div>'

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edit {html.escape(info["label"])} — CMS</title>
{ADMIN_CSS}
</head><body>
<header class="admin-header">
    <div class="admin-header-inner">
        <div class="admin-logo"><img src="https://pub-629428d185ca4960a0a73c850d32294b.r2.dev/company_61718/images/44fcd4c3-2756-4f76-91cd-ed604729d4d9.png" alt="Logo" height="28"> <span>Eyecosystems CMS</span></div>
        <div class="admin-header-right">
            <a href="/admin" class="btn-view">← Dashboard</a>
            <a href="/admin/logout" class="btn-logout">Logout</a>
        </div>
    </div>
</header>
<main class="admin-main">
    <h1>Editing: {html.escape(info["label"])}</h1>
    <p class="admin-desc">File: <code>{html.escape(info["file"])}</code></p>
    {msg}
    <form method="POST" action="/admin/save/{slug}" class="edit-form">
        {fields}
        <button type="submit" class="btn-save">Save Changes</button>
    </form>
</main>
</body></html>'''

def edit_post_page(post_slug, success="", error=""):
    fpath = SITE_ROOT / "blog" / post_slug / "index.html"
    if not fpath.exists():
        return "<h1>Post not found</h1>"
    page_html = fpath.read_text()
    regions = extract_editable_regions(page_html)
    rel_file = f"blog/{post_slug}/index.html"

    fields = ""
    for r in regions:
        esc_val = html.escape(r["value"])
        esc_raw = html.escape(r["raw"])
        is_long = len(r["value"]) > 100
        if is_long:
            fields += f'''<div class="field">
                <label>{html.escape(r["label"])}</label>
                <textarea name="val__{r["key"]}" rows="4">{esc_val}</textarea>
                <input type="hidden" name="raw__{r["key"]}" value="{esc_raw}">
                <input type="hidden" name="old__{r["key"]}" value="{esc_val}">
            </div>'''
        else:
            fields += f'''<div class="field">
                <label>{html.escape(r["label"])}</label>
                <input type="text" name="val__{r["key"]}" value="{esc_val}">
                <input type="hidden" name="raw__{r["key"]}" value="{esc_raw}">
                <input type="hidden" name="old__{r["key"]}" value="{esc_val}">
            </div>'''

    msg = ""
    if success:
        msg = '<div class="msg success">Changes saved successfully.</div>'
    if error:
        msg = f'<div class="msg error">{html.escape(error)}</div>'

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Edit Post — CMS</title>
{ADMIN_CSS}
</head><body>
<header class="admin-header">
    <div class="admin-header-inner">
        <div class="admin-logo"><img src="https://pub-629428d185ca4960a0a73c850d32294b.r2.dev/company_61718/images/44fcd4c3-2756-4f76-91cd-ed604729d4d9.png" alt="Logo" height="28"> <span>Eyecosystems CMS</span></div>
        <div class="admin-header-right">
            <a href="/admin" class="btn-view">← Dashboard</a>
            <a href="/admin/logout" class="btn-logout">Logout</a>
        </div>
    </div>
</header>
<main class="admin-main">
    <h1>Editing Post: {html.escape(post_slug.replace("-", " ").title())}</h1>
    <p class="admin-desc">File: <code>{html.escape(rel_file)}</code></p>
    {msg}
    <form method="POST" action="/admin/save-post/{post_slug}" class="edit-form">
        {fields}
        <button type="submit" class="btn-save">Save Changes</button>
    </form>
</main>
</body></html>'''

ADMIN_CSS = '''<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.admin-header{background:#1e293b;border-bottom:1px solid #334155;padding:0 24px;height:56px;display:flex;align-items:center;position:sticky;top:0;z-index:50}
.admin-header-inner{width:100%;max-width:1200px;margin:0 auto;display:flex;align-items:center;justify-content:space-between}
.admin-logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:16px}
.admin-logo img{height:28px}
.admin-header-right{display:flex;align-items:center;gap:12px}
.btn-view{background:#334155;color:#e2e8f0;padding:7px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;transition:background .15s}
.btn-view:hover{background:#475569}
.btn-logout{background:#7f1d1d;color:#fca5a5;padding:7px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;transition:background .15s}
.btn-logout:hover{background:#991b1b}
.admin-main{max-width:1200px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:28px;font-weight:700;margin-bottom:8px}
.admin-desc{font-size:14px;color:#94a3b8;margin-bottom:24px}
code{background:#334155;padding:2px 8px;border-radius:4px;font-size:13px}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{display:block;background:#1e293b;border:1px solid #334155;border-radius:10px;padding:24px;text-decoration:none;color:inherit;transition:border-color .15s,transform .1s}
.card:hover{border-color:#01a39e;transform:translateY(-2px)}
.card-label{font-size:17px;font-weight:700;margin-bottom:6px}
.card-path{font-size:13px;color:#64748b;font-family:monospace;margin-bottom:8px}
.card-mod{font-size:12px;color:#475569}
.edit-form{max-width:720px}
.field{margin-bottom:24px}
.field label{display:block;font-size:13px;font-weight:600;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
.field input[type="text"],.field textarea{width:100%;padding:12px 14px;background:#1e293b;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:15px;outline:none;transition:border .15s;font-family:inherit}
.field input[type="text"]:focus,.field textarea:focus{border-color:#00f5d0}
.field textarea{resize:vertical;line-height:1.6}
.btn-save{padding:14px 32px;background:#01a39e;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:background .15s}
.btn-save:hover{background:#019289}
.msg{padding:12px 16px;border-radius:8px;font-size:14px;margin-bottom:24px}
.msg.success{background:#14532d;color:#86efac;border:1px solid #166534}
.msg.error{background:#7f1d1d;color:#fca5a5;border:1px solid #991b1b}
</style>'''

# ── HTTP Handler ────────────────────────────────────────────────────────────
class CMSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def get_session_token(self):
        cookie_header = self.headers.get("Cookie", "")
        c = SimpleCookie()
        c.load(cookie_header)
        return c["cms_session"].value if "cms_session" in c else None

    def is_authed(self):
        return valid_session(self.get_session_token())

    def send_html(self, code, body, cookie=None):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())

    def redirect(self, location, cookie=None):
        self.send_response(302)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def read_post_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return urllib.parse.parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/admin" or path == "/admin/":
            if not self.is_authed():
                return self.send_html(200, login_page())
            return self.send_html(200, dashboard_page())

        if path.startswith("/admin/edit/"):
            if not self.is_authed():
                return self.redirect("/admin")
            slug = path.split("/admin/edit/")[1].strip("/")
            if slug in PAGES:
                return self.send_html(200, edit_page(slug, PAGES[slug]))
            return self.send_html(404, "<h1>Page not found</h1>")

        if path.startswith("/admin/edit-post/"):
            if not self.is_authed():
                return self.redirect("/admin")
            post_slug = path.split("/admin/edit-post/")[1].strip("/")
            return self.send_html(200, edit_post_page(post_slug))

        if path == "/admin/logout":
            tok = self.get_session_token()
            sessions.pop(tok, None)
            return self.redirect("/admin", "cms_session=deleted; Path=/; Max-Age=0")

        # Serve static files (the site itself)
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/admin/login":
            data = self.read_post_body()
            user = data.get("username", [""])[0]
            pw = data.get("password", [""])[0]
            pw_hash = hashlib.sha256(pw.encode()).hexdigest()
            if user == ADMIN_USER and pw_hash == ADMIN_PASS_HASH:
                tok = new_session()
                return self.redirect("/admin", f"cms_session={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_HOURS*3600}")
            return self.send_html(200, login_page("Invalid username or password."))

        if path.startswith("/admin/save/"):
            if not self.is_authed():
                return self.redirect("/admin")
            slug = path.split("/admin/save/")[1].strip("/")
            if slug not in PAGES:
                return self.send_html(404, "<h1>Not found</h1>")
            info = PAGES[slug]
            fpath = SITE_ROOT / info["file"]
            data = self.read_post_body()
            page_html = fpath.read_text()

            changes = 0
            for key in [k.replace("val__", "") for k in data if k.startswith("val__")]:
                new_val = data.get(f"val__{key}", [""])[0]
                old_val = data.get(f"old__{key}", [""])[0]
                old_raw = html.unescape(data.get(f"raw__{key}", [""])[0])
                if new_val != old_val and old_raw:
                    page_html = apply_text_edit(page_html, old_raw, old_val, new_val)
                    changes += 1

            if changes:
                fpath.write_text(page_html)
            return self.send_html(200, edit_page(slug, info, success=f"{changes} field(s) updated." if changes else "", error="" if changes else ""))

        if path.startswith("/admin/save-post/"):
            if not self.is_authed():
                return self.redirect("/admin")
            post_slug = path.split("/admin/save-post/")[1].strip("/")
            fpath = SITE_ROOT / "blog" / post_slug / "index.html"
            if not fpath.exists():
                return self.send_html(404, "<h1>Not found</h1>")
            data = self.read_post_body()
            page_html = fpath.read_text()

            changes = 0
            for key in [k.replace("val__", "") for k in data if k.startswith("val__")]:
                new_val = data.get(f"val__{key}", [""])[0]
                old_val = data.get(f"old__{key}", [""])[0]
                old_raw = html.unescape(data.get(f"raw__{key}", [""])[0])
                if new_val != old_val and old_raw:
                    page_html = apply_text_edit(page_html, old_raw, old_val, new_val)
                    changes += 1

            if changes:
                fpath.write_text(page_html)
            return self.send_html(200, edit_post_page(post_slug, success=f"{changes} field(s) updated." if changes else ""))

    def log_message(self, format, *args):
        if "/admin" in (args[0] if args else ""):
            super().log_message(format, *args)

if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), CMSHandler)
    print(f"\n  Eyecosystems CMS running at http://localhost:{PORT}/admin")
    print(f"  Site preview at http://localhost:{PORT}/")
    print(f"  Login: {ADMIN_USER} / eyeco2027\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
