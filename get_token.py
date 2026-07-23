# -*- coding: utf-8 -*-
"""飞球直播 token 自动获取（易盾 createNEGuardian，无需人工点验证码）"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
TOKEN_JSON = ROOT / "token.json"
TOKEN_TXT = ROOT / "token.txt"

DEFAULTS = {
    "home_url": "https://www.fqzb161.com/home",
    "base_im_api": "https://openim-php-api.qaek4a2wjx6bt.cc",
    "version": "1.9.7",
    "api_version": "8",
    "platform": "fqzb",
    "product_id": "YD00822260586227",
}


def load_config() -> dict:
    cfg = {**DEFAULTS}
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    # 环境变量优先（GitHub Actions / Render secrets）
    if os.environ.get("FQZB_ACCOUNT"):
        cfg["account"] = os.environ["FQZB_ACCOUNT"]
    if os.environ.get("FQZB_PASSWORD"):
        cfg["password"] = os.environ["FQZB_PASSWORD"]
    if os.environ.get("FQZB_HOME_URL"):
        cfg["home_url"] = os.environ["FQZB_HOME_URL"]
    if os.environ.get("FQZB_BASE_IM_API"):
        cfg["base_im_api"] = os.environ["FQZB_BASE_IM_API"]
    if not cfg.get("account") or not cfg.get("password"):
        raise SystemExit("需要账号密码：config.json 或环境变量 FQZB_ACCOUNT / FQZB_PASSWORD")
    return cfg


def decode_jwt_payload(token: str):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(parts[1] + pad).decode("utf-8"))
    except Exception:
        return None


def get_yidun_tokens(home_url: str, product_id: str) -> dict:
    """?????????? SDK??? fingerprint + protector token?"""
    js = """
    async () => {
      const out = {};
      try {
        if (window.FingerprintJS) {
          const fp = await FingerprintJS.load();
          const r = await fp.get();
          out.fingerprint = r.visitorId;
          localStorage.setItem('fingerprintVal', r.visitorId);
        }
      } catch (e) { out.fp_err = String(e); }

      // FingerprintJS ? GitHub Actions ?????????? 32 hex ?? imei
      if (!out.fingerprint) {
        try {
          const bytes = new Uint8Array(16);
          crypto.getRandomValues(bytes);
          out.fingerprint = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
          localStorage.setItem('fingerprintVal', out.fingerprint);
        } catch (e) { out.fp_fallback_err = String(e); }
      }

      try {
        const capRes = await fetch('https://openim-php-api.qaek4a2wjx6bt.cc/v220/captcha', {
          headers: {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'version': '1.9.7',
            'device': '3',
            'api-version': '8',
            'platform': 'fqzb',
            'device2': '3',
            'imei': localStorage.getItem('fingerprintVal') || '',
          }
        });
        out.captcha = await capRes.json();
        const pid = (out.captcha && out.captcha.data && out.captcha.data.product_id) || 'YD00822260586227';
        localStorage.setItem('YiDunId', pid);
        out.product_id = pid;
      } catch (e) { out.cap_err = String(e); }

      try {
        const productId = out.product_id || 'YD00822260586227';
        const g = createNEGuardian({ productId, timeout: 10000 });
        const t1 = await g.getToken({});
        out.guardian = t1;
        if (t1 && (t1.code === 200 || t1.code === 201) && t1.token) {
          localStorage.setItem('YiDunProtectorIds', t1.token);
          out.yidun_token = t1.token;
        }
      } catch (e) { out.g_err = String(e); }

      return out;
    }
    """

    # ????????????GitHub Actions ?????? window????????
    sdk_urls = [
        "https://resource-rr.opajann.cn/web_js/public/fp.min.js",
        "https://resource-rr.opajann.cn/web_js/public/YiDunProtector-Web-2.1.1.js",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = browser.new_page(
            viewport={"width": 1365, "height": 900},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        print(f"[*] ???????? SDK: {home_url}", flush=True)
        page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            page.wait_for_function("typeof createNEGuardian === 'function'", timeout=15000)
        except PlaywrightTimeoutError:
            print("[!] ?????? createNEGuardian????????? SDK...", flush=True)
            for url in sdk_urls:
                try:
                    print(f"[*] inject {url}", flush=True)
                    page.add_script_tag(url=url)
                    page.wait_for_timeout(1200)
                except Exception as e:
                    print(f"[!] inject failed: {url} -> {e}", flush=True)
            try:
                page.wait_for_function("typeof createNEGuardian === 'function'", timeout=20000)
            except PlaywrightTimeoutError as e:
                debug = page.evaluate(
                    """() => ({
                      href: location.href,
                      title: document.title,
                      readyState: document.readyState,
                      hasGuardian: typeof createNEGuardian,
                      hasFP: typeof FingerprintJS,
                      scripts: Array.from(document.scripts).map(s => s.src).filter(Boolean).slice(0, 30),
                      text: (document.body && document.body.innerText || '').slice(0, 300)
                    })"""
                )
                browser.close()
                raise RuntimeError("?? SDK ????: " + json.dumps(debug, ensure_ascii=False)) from e

        page.wait_for_timeout(800)
        data = page.evaluate(js)
        browser.close()
    return data

def login_pass(cfg: dict, yidun: dict) -> dict:
    base = cfg["base_im_api"].rstrip("/")
    url = f"{base}/v220/user/login/pass"
    yidun_token = yidun.get("yidun_token") or ""
    if not yidun_token:
        raise RuntimeError(f"未拿到易盾 token: {json.dumps(yidun, ensure_ascii=False)[:500]}")

    fingerprint = yidun.get("fingerprint") or ""
    body = urllib.parse.urlencode(
        {
            "account": cfg["account"],
            "pass": cfg["password"],
            # 实测：易盾 protector token 可直接作为 captcha_validate
            "captcha_validate": yidun_token,
        }
    ).encode("utf-8")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "version": str(cfg.get("version", "1.9.7")),
        "device": "3",
        "api-version": str(cfg.get("api_version", "8")),
        "platform": str(cfg.get("platform", "fqzb")),
        "device2": "3",
        "imei": fingerprint,
        "dun-imei": yidun_token,
        "Origin": "https://www.fqzb161.com",
        "Referer": "https://www.fqzb161.com/",
    }

    print(f"[*] POST {url}", flush=True)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def save_token(payload: dict) -> None:
    TOKEN_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    token = payload.get("token") or ""
    TOKEN_TXT.write_text((token + "\n") if token else "", encoding="utf-8")
    print(f"[OK] {TOKEN_JSON}", flush=True)
    print(f"[OK] {TOKEN_TXT}", flush=True)
    if token:
        print(f"[OK] token: {token[:72]}...", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="飞球直播自动获取 token")
    ap.add_argument("--account", default="")
    ap.add_argument("--password", default="")
    args = ap.parse_args()

    cfg = load_config()
    if args.account:
        cfg["account"] = args.account
    if args.password:
        cfg["password"] = args.password

    yidun = get_yidun_tokens(cfg["home_url"], cfg.get("product_id", DEFAULTS["product_id"]))
    print(f"[*] fingerprint={yidun.get('fingerprint')}", flush=True)
    yt = yidun.get("yidun_token") or ""
    print(f"[*] yidun_token={yt[:24]}...", flush=True)

    result = login_pass(cfg, yidun)
    print(f"[*] login code={result.get('code')} message={result.get('message')}", flush=True)
    if result.get("code") != 200:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(2)

    data = result.get("data") or {}
    token = data.get("access_token") or ""
    if not token:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        raise SystemExit(2)

    payload = {
        "token": token,
        "im_token": data.get("im_token"),
        "chat_token": data.get("chat_token"),
        "account": cfg["account"],
        "userinfos": {
            "id": data.get("id"),
            "userid": data.get("userid"),
            "user_id": data.get("user_id"),
            "user_nickname": data.get("user_nickname"),
            "email": data.get("email"),
            "im_uid": data.get("im_uid"),
            "portrait": data.get("portrait"),
            "grade": data.get("grade"),
            "coin_num": data.get("coin_num"),
            "diamond_num": data.get("diamond_num"),
        },
        "fingerprintVal": yidun.get("fingerprint"),
        "YiDunProtectorIds": yidun.get("yidun_token"),
        "source": "yidun+api",
        "jwt_payload": decode_jwt_payload(token),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_token(payload)


if __name__ == "__main__":
    main()
