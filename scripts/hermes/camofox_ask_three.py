#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9377"
USER_ID = "hermes-issue-43"
DEFAULT_TIMEOUT = 120


def request(method, path, payload=None, timeout=45):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {raw}") from exc
    return json.loads(raw) if raw else {}


def ref_from_line(line):
    match = re.search(r"\[(e\d+)\]", line)
    return match.group(1) if match else None


def create_tab(provider, url):
    res = request(
        "POST",
        "/tabs",
        {"userId": USER_ID, "sessionKey": f"ask-three-{provider}-{int(time.time())}", "url": url},
    )
    return res["tabId"]


def snapshot(tab_id):
    res = request("GET", f"/tabs/{tab_id}/snapshot?userId={USER_ID}", timeout=35)
    return res.get("snapshot", "")


def find_ref(snap, needles):
    for line in snap.splitlines():
        lower = line.lower()
        if all(needle.lower() in lower for needle in needles):
            ref = ref_from_line(line)
            if ref:
                return ref
    return None


def is_deepseek_login_required(snap):
    lower = snap.lower()
    login_markers = [
        "phone number / email address",
        "forgot password",
        "sign up or log in",
        "signing up or logging in",
    ]
    return any(marker in lower for marker in login_markers)


def find_deepseek_textbox(snap):
    candidates = [
        ["textbox", "Message DeepSeek"],
        ["textbox", "message"],
        ["textbox", "ask"],
        ["textbox"],
        ["textarea"],
        ["contenteditable"],
    ]
    for needles in candidates:
        ref = find_ref(snap, needles)
        if ref:
            return ref
    return None


def write_debug_snapshot(name, snap):
    path = f"/Users/bobeenlee/.hermes/camofox-server/{name}"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(snap)
    except OSError:
        pass


def type_text(tab_id, ref, text, press_enter=False):
    return request(
        "POST",
        f"/tabs/{tab_id}/type",
        {"userId": USER_ID, "ref": ref, "text": text, "pressEnter": press_enter},
        timeout=35,
    )


def click(tab_id, ref):
    return request("POST", f"/tabs/{tab_id}/click", {"userId": USER_ID, "ref": ref}, timeout=35)


def clean_text(line):
    text = line.split(":", 1)[-1].strip().strip('"')
    text = re.sub(r"\s+", " ", text)
    return text


def extract_reply(snap, prompt):
    lines = snap.splitlines()
    prompt_seen = False
    chunks = []
    for line in lines:
        if prompt[:80] in line or prompt in line:
            prompt_seen = True
            continue
        if not prompt_seen:
            continue
        if any(marker in line for marker in ["Response actions", "Copy response", "ChatGPT can make mistakes", "textbox \"Chat with ChatGPT\"", "Add files and more"]):
            break
        if any(marker in line for marker in ["textbox ", "Message DeepSeek", "Gemini 프롬프트 입력", "Chat with ChatGPT"]):
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in stripped for token in ["paragraph:", "- text:", "- listitem:", "heading "]):
            text = clean_text(stripped)
            if text and prompt[:40] not in text and text not in chunks:
                chunks.append(text)
    return "\n".join(chunks).strip()


def wait_reply(tab_id, prompt, timeout=DEFAULT_TIMEOUT):
    deadline = time.time() + timeout
    best = ""
    stable_polls = 0
    while time.time() < deadline:
        snap = snapshot(tab_id)
        reply = extract_reply(snap, prompt)
        if len(reply) > len(best):
            best = reply
            stable_polls = 0
        elif len(best) > 120:
            stable_polls += 1
        lower_snap = snap.lower()
        busy_markers = [
            "generating",
            "stop generating",
            "stop responding",
            "응답 중지",
            "생성 중지",
            "답변 생성 중",
        ]
        if len(best) > 120 and not any(marker in lower_snap for marker in busy_markers):
            time.sleep(3)
            newer = extract_reply(snapshot(tab_id), prompt)
            return newer or best
        if stable_polls >= 3:
            return best
        time.sleep(5)
    return best or "ERROR_NOT_SEEN"


def run_chatgpt(prompt):
    tab = create_tab("chatgpt", "https://chatgpt.com/")
    time.sleep(4)
    snap = snapshot(tab)
    ref = find_ref(snap, ["textbox", "chatgpt"]) or find_ref(snap, ["Ask anything"])
    if not ref:
        return "ERROR_NO_TEXTBOX"
    type_text(tab, ref, prompt, press_enter=True)
    return wait_reply(tab, prompt)


def run_gemini(prompt):
    tab = create_tab("gemini", "https://gemini.google.com/app")
    time.sleep(5)
    snap = snapshot(tab)
    ref = find_ref(snap, ["textbox", "Gemini"])
    if not ref:
        return "ERROR_NO_TEXTBOX"
    type_text(tab, ref, prompt, press_enter=True)
    time.sleep(2)
    snap = snapshot(tab)
    if prompt[:80] in snap and "Gemini의 응답" not in snap:
        send_ref = find_ref(snap, ["button", "메시지 보내기"])
        if send_ref:
            click(tab, send_ref)
    return wait_reply(tab, prompt)


def run_deepseek(prompt):
    tab = create_tab("deepseek", "https://chat.deepseek.com/")
    time.sleep(5)
    snap = snapshot(tab)
    reload_ref = find_ref(snap, ["button", "Reload"])
    if reload_ref:
        click(tab, reload_ref)
        time.sleep(6)
        snap = snapshot(tab)

    instant_ref = find_ref(snap, ["radio", "Instant"])
    instant_area = snap.split('radio "Expert"')[0] if 'radio "Expert"' in snap else snap
    if instant_ref and "[checked]" not in instant_area:
        click(tab, instant_ref)
        time.sleep(1)
        snap = snapshot(tab)

    if is_deepseek_login_required(snap):
        write_debug_snapshot("deepseek_login_required_snapshot.txt", snap)
        return "ERROR_LOGIN_REQUIRED"

    ref = find_deepseek_textbox(snap)
    if not ref:
        write_debug_snapshot("deepseek_textbox_not_found_snapshot.txt", snap)
        return "ERROR_DEEPSEEK_TEXTBOX_NOT_FOUND"
    type_text(tab, ref, prompt, press_enter=False)
    time.sleep(1)
    snap = snapshot(tab)

    button_refs = []
    after_box = False
    for line in snap.splitlines():
        if ref in line or "Message DeepSeek" in line:
            after_box = True
        elif after_box and "- button" in line:
            ref = ref_from_line(line)
            if ref:
                button_refs.append(ref)

    for ref in reversed(button_refs[-4:]):
        try:
            click(tab, ref)
        except Exception:
            continue
        time.sleep(8)
        snap = snapshot(tab)
        if prompt[:80] not in snap or extract_reply(snap, prompt):
            reply = wait_reply(tab, prompt, timeout=90)
            if not reply.startswith("ERROR"):
                return reply
    return wait_reply(tab, prompt, timeout=60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--providers", default="chatgpt,gemini,deepseek")
    args = parser.parse_args()

    runners = {
        "chatgpt": run_chatgpt,
        "gemini": run_gemini,
        "deepseek": run_deepseek,
    }
    results = {}
    for provider in [p.strip() for p in args.providers.split(",") if p.strip()]:
        try:
            results[provider] = runners[provider](args.prompt)
        except Exception as exc:
            results[provider] = f"ERROR: {exc}"
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
