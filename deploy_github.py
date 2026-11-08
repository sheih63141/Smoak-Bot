#!/usr/bin/env python3
"""
Полный деплой бота на GitHub: создаёт репозиторий, заливает код,
кладёт токен в секреты и запускает workflow. Ничего вручную.

Требуется токен GitHub (classic PAT с правами repo + workflow):
  github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)
  → Generate new token → галочки: repo, workflow

Запуск:
  GH_TOKEN=ghp_xxx DISCORD_TOKEN=xxx python3 deploy_github.py [имя-репозитория]
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO_NAME = (sys.argv[1] if len(sys.argv) > 1 else "smoak-bot").strip()
HERE = os.path.dirname(os.path.abspath(__file__))

GH = os.getenv("GH_TOKEN", "").strip()
DISCORD = os.getenv("DISCORD_TOKEN", "").strip()


def call(method: str, path: str, data=None, raw=False):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {GH}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read()
            return (r.status, payload if raw else (json.loads(payload) if payload else {}))
    except urllib.error.HTTPError as e:
        return (e.code, json.loads(e.read() or b"{}"))


def step(n: str, text: str) -> None:
    print(f"\n[{n}] {text}")


def main() -> int:
    if not GH:
        print("❌ Нужен GH_TOKEN — токен GitHub (repo + workflow)")
        return 1
    if not DISCORD:
        print("❌ Нужен DISCORD_TOKEN — токен бота")
        return 1

    # ---------- 1. кто мы ----------
    step("1/6", "проверяю токен GitHub")
    code, user = call("GET", "/user")
    if code != 200:
        print(f"❌ токен не принят GitHub: {code} {user.get('message', '')}")
        return 1
    owner = user["login"]
    print(f"    ✅ вошёл как {owner}")

    # ---------- 2. репозиторий ----------
    step("2/6", f"создаю репозиторий {owner}/{REPO_NAME}")
    code, repo = call("GET", f"/repos/{owner}/{REPO_NAME}")
    if code == 200:
        print("    уже существует — переиспользую")
    else:
        code, repo = call("POST", "/user/repos", {
            "name": REPO_NAME,
            "private": False,          # публичный = безлимит минут Actions
            "description": "SmoakTeam Discord bot",
            "auto_init": False,
        })
        if code not in (201, 200):
            print(f"❌ не смог создать: {code} {repo.get('message', '')}")
            return 1
        print(f"    ✅ {repo['html_url']}")

    clone_url = repo.get("clone_url") or f"https://github.com/{owner}/{REPO_NAME}.git"

    # ---------- 3. пуш кода ----------
    step("3/6", "заливаю код")
    git = ["git", "-c", f"http.extraHeader=Authorization: Bearer {GH}"]
    existing = subprocess.run(["git", "remote", "get-url", "origin"],
                              cwd=HERE, capture_output=True, text=True)
    if existing.returncode == 0:
        subprocess.run(["git", "remote", "set-url", "origin", clone_url], cwd=HERE, check=True)
    else:
        subprocess.run(git + ["remote", "add", "origin", clone_url], cwd=HERE, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=HERE, capture_output=True)
    push = subprocess.run(git + ["push", "-f", "origin", "main"],
                          cwd=HERE, capture_output=True, text=True)
    if push.returncode != 0:
        print("❌ пуш не удался:")
        print(push.stderr[-1500:])
        return 1
    print("    ✅ код в репозитории")

    # ---------- 4. секрет ----------
    step("4/6", "кладу DISCORD_TOKEN в секреты Actions")
    try:
        from nacl import encoding, public
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pynacl"], check=True)
        from nacl import encoding, public

    code, key = call("GET", f"/repos/{owner}/{REPO_NAME}/actions/secrets/public-key")
    if code != 200:
        print(f"❌ нет публичного ключа: {code} {key.get('message', '')}")
        return 1
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(DISCORD.encode())
    code, res = call("PUT", f"/repos/{owner}/{REPO_NAME}/actions/secrets/DISCORD_TOKEN", {
        "encrypted_value": base64.b64encode(sealed).decode(),
        "key_id": key["key_id"],
    })
    if code not in (201, 204):
        print(f"❌ секрет не создан: {code} {res.get('message', '')}")
        return 1
    print("    ✅ секрет DISCORD_TOKEN сохранён")

    # ---------- 5. запуск ----------
    step("5/6", "запускаю workflow")
    time.sleep(3)   # даём GitHub подхватить файл workflow
    code, res = call("POST", f"/repos/{owner}/{REPO_NAME}/actions/workflows/bot.yml/dispatches",
                     {"ref": "main"})
    if code not in (204, 201):
        # возможно, workflow ещё не проиндексирован — пробуем ещё раз
        time.sleep(10)
        code, res = call("POST", f"/repos/{owner}/{REPO_NAME}/actions/workflows/bot.yml/dispatches",
                         {"ref": "main"})
    if code in (204, 201):
        print("    ✅ бот запускается")
    else:
        print(f"    ⚠️ автозапуск не сработал ({code}): запустите вручную — Actions → SmoakTeam bot → Run workflow")

    # ---------- 6. ждём лог ----------
    step("6/6", "смотрю логи запуска")
    run_id = None
    for _ in range(12):
        time.sleep(10)
        code, runs = call("GET", f"/repos/{owner}/{REPO_NAME}/actions/workflows/bot.yml/runs?per_page=1")
        if code == 200 and runs.get("workflow_runs"):
            r = runs["workflow_runs"][0]
            run_id = r["id"]
            print(f"    статус: {r.get('status')} / {r.get('conclusion')}")
            if r.get("status") in ("in_progress", "completed"):
                break

    if run_id:
        code, jobs = call("GET", f"/repos/{owner}/{REPO_NAME}/actions/runs/{run_id}/jobs")
        ok = any("Бот на связи" in (step_log or "")
                 for j in jobs.get("jobs", []) for step_log in [str(j)])
        print(f"\n🌍 Репозиторий: https://github.com/{owner}/{REPO_NAME}")
        print(f"🔧 Логи: https://github.com/{owner}/{REPO_NAME}/actions")
        print("\nПроверьте лог шага «Запускаю бота» — должно быть «Бот на связи».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
