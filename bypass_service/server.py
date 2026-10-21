"""
Standalone REST API Server & Web UI Dashboard for Course Wallah Bypass Service
Run with:
    python -m bypass_service.server
    or
    python bypass_service/server.py
"""

import os
import sys
import time
from flask import Flask, request, jsonify, render_template_string
from .engine import default_engine, BypassEngine

app = Flask(__name__)
SERVER_START_TIME = time.time()

# HTML Dashboard Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Course Wallah ⚡ Bypass Engine</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #090a0f;
            --card-bg: rgba(18, 20, 32, 0.75);
            --border-glow: rgba(0, 240, 255, 0.25);
            --neon-cyan: #00f0ff;
            --neon-pink: #ff0077;
            --neon-green: #00ff88;
            --text-main: #f0f4fc;
            --text-dim: #8a99b5;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', -apple-system, sans-serif;
        }

        body {
            background-color: var(--bg-dark);
            background-image: 
                radial-gradient(circle at 15% 20%, rgba(0, 240, 255, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 85% 80%, rgba(255, 0, 119, 0.08) 0%, transparent 40%),
                linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
            background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }

        .container {
            width: 100%;
            max-width: 840px;
        }

        header {
            text-align: center;
            margin-bottom: 35px;
        }

        .badge-tag {
            display: inline-block;
            padding: 5px 14px;
            background: rgba(0, 240, 255, 0.1);
            border: 1px solid rgba(0, 240, 255, 0.3);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            color: var(--neon-cyan);
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 12px;
        }

        h1 {
            font-size: 2.8rem;
            font-weight: 900;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff 30%, var(--neon-cyan) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }

        p.subtitle {
            color: var(--text-dim);
            font-size: 1.05rem;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-glow);
            backdrop-filter: blur(16px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            margin-bottom: 25px;
        }

        .input-group {
            display: flex;
            gap: 12px;
            margin-bottom: 15px;
        }

        input[type="text"] {
            flex: 1;
            padding: 16px 20px;
            background: rgba(10, 12, 20, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            color: #fff;
            font-size: 1rem;
            outline: none;
            transition: all 0.25s ease;
        }

        input[type="text"]:focus {
            border-color: var(--neon-cyan);
            box-shadow: 0 0 16px rgba(0, 240, 255, 0.3);
        }

        button.btn-bypass {
            padding: 16px 32px;
            background: linear-gradient(135deg, #00f0ff, #0077fe);
            border: none;
            border-radius: 12px;
            color: #050811;
            font-weight: 700;
            font-size: 1.05rem;
            cursor: pointer;
            transition: all 0.25s ease;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
        }

        button.btn-bypass:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0, 240, 255, 0.4);
        }

        button.btn-bypass:active {
            transform: translateY(0);
        }

        /* Results Box */
        .result-box {
            display: none;
            margin-top: 25px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            padding-top: 25px;
            animation: fadeIn 0.4s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }

        .status-pill {
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 10px;
            text-transform: uppercase;
        }

        .status-success { background: rgba(0, 255, 136, 0.15); color: var(--neon-green); border: 1px solid rgba(0, 255, 136, 0.3); }
        .status-error { background: rgba(255, 0, 119, 0.15); color: var(--neon-pink); border: 1px solid rgba(255, 0, 119, 0.3); }

        .url-display {
            background: #06070c;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 14px 18px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.95rem;
            color: var(--neon-green);
            word-break: break-all;
            margin-bottom: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
        }

        .btn-group {
            display: flex;
            gap: 10px;
        }

        .btn-action {
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .btn-copy {
            background: rgba(255, 255, 255, 0.08);
            color: #fff;
        }
        .btn-copy:hover { background: rgba(255, 255, 255, 0.15); }

        .btn-open {
            background: var(--neon-cyan);
            color: #06070c;
        }
        .btn-open:hover { background: #5ef4ff; }

        .meta-stats {
            display: flex;
            gap: 20px;
            font-size: 13px;
            color: var(--text-dim);
            margin-top: 12px;
        }

        .stat-item b {
            color: var(--text-main);
        }

        /* Supported Networks Grid */
        .supported-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }

        .grid-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 13px;
            font-weight: 500;
            text-align: center;
            color: var(--text-dim);
            transition: all 0.2s;
        }

        .grid-item:hover {
            color: var(--neon-cyan);
            border-color: rgba(0, 240, 255, 0.4);
            background: rgba(0, 240, 255, 0.05);
        }

        /* API Integration block */
        .api-card {
            background: #06070e;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 18px;
            margin-top: 25px;
        }

        .api-card pre {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: #8be9fd;
            overflow-x: auto;
            margin-top: 8px;
        }
    </style>
</head>
<body>

<div class="container">
    <header>
        <span class="badge-tag">Engine v1.0.0</span>
        <h1>Course Wallah Bypass Engine</h1>
        <p class="subtitle">Instant unshortening for Indian shorteners, Ad walls & File hosters</p>
    </header>

    <div class="card">
        <form id="bypassForm" onsubmit="handleBypass(event)">
            <div class="input-group">
                <input type="text" id="targetUrl" placeholder="Paste shortlink (e.g. https://gplinks.co/..., droplink, tinyurl, modsfire...)" required autocomplete="off">
                <button type="submit" class="btn-bypass" id="submitBtn">
                    <span>⚡ Bypass</span>
                </button>
            </div>
        </form>

        <div id="resultBox" class="result-box">
            <div class="result-header">
                <span id="statusBadge" class="status-pill status-success">Success</span>
                <span id="timeBadge" style="font-size:12px;color:var(--text-dim);"></span>
            </div>
            <div class="url-display">
                <span id="bypassedUrlText"></span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="meta-stats">
                    <span class="stat-item">Handler: <b id="handlerText"></b></span>
                    <span class="stat-item">Hops: <b id="hopsText"></b></span>
                    <span class="stat-item">Cached: <b id="cachedText"></b></span>
                </div>
                <div class="btn-group">
                    <button class="btn-action btn-copy" onclick="copyResult()">📋 Copy</button>
                    <a id="openLinkBtn" class="btn-action btn-open" target="_blank" rel="noopener">🚀 Open</a>
                </div>
            </div>
        </div>
    </div>

    <div class="card">
        <h3 style="font-size:1.1rem; margin-bottom:5px;">Supported Networks & Engines</h3>
        <p style="font-size:13px; color:var(--text-dim); margin-bottom:15px;">Includes 400+ domains from bypass-shortlinks & Indian Go-Link networks</p>
        <div class="supported-grid">
            <div class="grid-item">GPLinks</div>
            <div class="grid-item">Droplink</div>
            <div class="grid-item">ShrinkMe</div>
            <div class="grid-item">Rocklinks</div>
            <div class="grid-item">VPLink</div>
            <div class="grid-item">SoftURL</div>
            <div class="grid-item">Linkshortify</div>
            <div class="grid-item">Lksfy</div>
            <div class="grid-item">Modsfire</div>
            <div class="grid-item">Cloudfam</div>
            <div class="grid-item">Uploady</div>
            <div class="grid-item">Mega4Upload</div>
            <div class="grid-item">TinyURL</div>
            <div class="grid-item">Bitly</div>
            <div class="grid-item">Base64 Hops</div>
            <div class="grid-item">AdLinkFly</div>
        </div>

        <div class="api-card">
            <div style="font-size:13px; font-weight:600; color:var(--text-dim);">REST API Quick Call</div>
            <pre>curl -X POST http://localhost:5055/api/bypass -H "Content-Type: application/json" -d '{"url":"https://tinyurl.com/2p9c7n42"}'</pre>
        </div>
    </div>
</div>

<script>
    async function handleBypass(e) {
        e.preventDefault();
        const input = document.getElementById('targetUrl');
        const btn = document.getElementById('submitBtn');
        const resultBox = document.getElementById('resultBox');
        const url = input.value.trim();

        if (!url) return;

        btn.disabled = true;
        btn.innerHTML = '<span>⏳ Resolving...</span>';

        try {
            const res = await fetch('/api/bypass', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            const data = await res.json();

            resultBox.style.display = 'block';
            const badge = document.getElementById('statusBadge');
            const timeBadge = document.getElementById('timeBadge');
            const urlText = document.getElementById('bypassedUrlText');
            const handlerText = document.getElementById('handlerText');
            const hopsText = document.getElementById('hopsText');
            const cachedText = document.getElementById('cachedText');
            const openBtn = document.getElementById('openLinkBtn');

            if (data.success) {
                badge.className = 'status-pill status-success';
                badge.innerText = 'Unlocked';
                timeBadge.innerText = `${data.time_ms} ms`;
                urlText.innerText = data.bypassed_url;
                handlerText.innerText = data.handler || 'Direct';
                hopsText.innerText = data.hops || 1;
                cachedText.innerText = data.cached ? 'Yes' : 'No';
                openBtn.href = data.bypassed_url;
                openBtn.style.display = 'inline-flex';
            } else {
                badge.className = 'status-pill status-error';
                badge.innerText = 'No Redirect Found';
                timeBadge.innerText = `${data.time_ms} ms`;
                urlText.innerText = data.original_url;
                handlerText.innerText = 'None';
                hopsText.innerText = 0;
                cachedText.innerText = 'No';
                openBtn.style.display = 'none';
            }
        } catch(err) {
            alert('Failed to connect to Bypass API: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span>⚡ Bypass</span>';
        }
    }

    function copyResult() {
        const text = document.getElementById('bypassedUrlText').innerText;
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            alert('Copied bypassed link to clipboard!');
        });
    }
</script>
</body>
</html>
"""


# Enable CORS on all responses
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response


@app.route('/', methods=['GET'])
@app.route('/bypass', methods=['GET'])
def index():
    # If ?url= is passed to /bypass, return json or resolve
    url_param = request.args.get('url')
    if url_param and request.headers.get('Accept', '').startswith('application/json'):
        return jsonify(default_engine.bypass(url_param))
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/bypass', methods=['GET', 'POST', 'OPTIONS'])
def api_bypass():
    if request.method == 'OPTIONS':
        return ('', 204)

    target_url = None
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        target_url = data.get('url') or request.form.get('url')
    else:
        target_url = request.args.get('url')

    if not target_url:
        return jsonify({
            "success": False,
            "error": "Missing 'url' parameter in request (JSON body or query parameter)",
            "example": {
                "method": "POST",
                "body": {"url": "https://gplinks.co/example"}
            }
        }), 400

    result = default_engine.bypass(target_url)
    return jsonify(result)


@app.route('/api/health', methods=['GET'])
def api_health():
    uptime_sec = round(time.time() - SERVER_START_TIME, 1)
    return jsonify({
        "status": "online",
        "service": "Course Wallah Bypass Engine",
        "version": "1.0.0",
        "uptime_seconds": uptime_sec,
        "cache_entries": len(default_engine._cache)
    })


@app.route('/api/supported', methods=['GET'])
def api_supported():
    return jsonify({
        "service": "Course Wallah Bypass Service",
        "categories": [
            {
                "name": "Indian Shortener Networks",
                "examples": ["gplinks.co", "droplink.co", "shrinkme.io", "rocklinks.in", "vplink.in", "softurl.in", "lksfy.in", "linkshortify.in", "4hi.in", "dekhe.click", "clk.sh", "srnky.com"]
            },
            {
                "name": "File Hosters",
                "examples": ["modsfire.com", "cloudfam.io", "uploady.io", "mega4upload.net", "dailyuploads.net", "jioupload.link", "frdl.io"]
            },
            {
                "name": "Generic URL Shorteners",
                "examples": ["tinyurl.com", "bit.ly", "is.gd", "t.co", "rebrand.ly", "buff.ly", "s.id"]
            },
            {
                "name": "Direct Parameter / Base64 Redirects",
                "examples": ["?r=aHR0c...", "?url=...", "?dest=...", "?target=..."]
            }
        ]
    })


def run_server(host: str = "0.0.0.0", port: int = 5055, debug: bool = False):
    print(f"🚀 Course Wallah Bypass API running on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    port = int(os.environ.get("BYPASS_PORT", 5055))
    run_server(port=port)
