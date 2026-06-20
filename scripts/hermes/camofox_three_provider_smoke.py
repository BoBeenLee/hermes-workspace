#!/usr/bin/env python3
import json
import re
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9377"
USER_ID = "hermes-issue-43"
PROMPTS = {
    "chatgpt": "Hermes agent terminal-adapter ChatGPT smoke test. Reply only 정상.",
    "gemini": "Hermes agent terminal-adapter Gemini smoke test. Reply only 정상.",
    "deepseek": "Hermes agent terminal-adapter DeepSeek smoke test. Reply only 정상.",
}


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
        {"userId": USER_ID, "sessionKey": f"hermes-terminal-{provider}", "url": url},
    )
    return res["tabId"]


def snapshot(tab_id):
    res = request("GET", f"/tabs/{tab_id}/snapshot?userId={USER_ID}", timeout=30)
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
        timeout=30,
    )


def click(tab_id, ref):
    return request("POST", f"/tabs/{tab_id}/click", {"userId": USER_ID, "ref": ref}, timeout=30)


def extract_reply(snap, prompt):
    lines = snap.splitlines()
    prompt_seen = False
    candidates = []
    for line in lines:
        if prompt in line:
            prompt_seen = True
            continue
        if prompt_seen and ("paragraph:" in line or "- text:" in line):
            text = line.split(":", 1)[-1].strip().strip('"')
            if text and prompt not in text:
                candidates.append(text)
    for text in candidates:
        if "정상" in text:
            return text
    return candidates[-1] if candidates else ""


def wait_reply(tab_id, prompt, timeout=75):
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        snap = snapshot(tab_id)
        last = extract_reply(snap, prompt)
        if "정상" in last:
            return last
        time.sleep(5)
    return last or "ERROR_NOT_SEEN"


def run_chatgpt():
    tab = create_tab("chatgpt", "https://chatgpt.com/")
    time.sleep(4)
    snap = snapshot(tab)
    ref = find_ref(snap, ["textbox", "chatgpt"]) or find_ref(snap, ["Ask anything"])
    if not ref:
        return "ERROR_NO_TEXTBOX"
    type_text(tab, ref, PROMPTS["chatgpt"], press_enter=True)
    return wait_reply(tab, PROMPTS["chatgpt"])


def run_gemini():
    tab = create_tab("gemini", "https://gemini.google.com/app")
    time.sleep(4)
    snap = snapshot(tab)
    ref = find_ref(snap, ["textbox", "Gemini"])
    if not ref:
        return "ERROR_NO_TEXTBOX"
    type_text(tab, ref, PROMPTS["gemini"], press_enter=True)
    time.sleep(2)
    snap = snapshot(tab)
    if PROMPTS["gemini"] in snap and "Gemini의 응답" not in snap:
        send_ref = find_ref(snap, ["button", "메시지 보내기"])
        if send_ref:
            click(tab, send_ref)
    return wait_reply(tab, PROMPTS["gemini"])


def run_deepseek():
    tab = create_tab("deepseek", "https://chat.deepseek.com/")
    time.sleep(5)
    snap = snapshot(tab)
    reload_ref = find_ref(snap, ["button", "Reload"])
    if reload_ref:
        click(tab, reload_ref)
        time.sleep(6)
        snap = snapshot(tab)

    if 'radio "Instant"' in snap and 'radio "Instant"' in snap.split('radio "Expert"')[0] and "[checked]" not in snap.split('radio "Expert"')[0]:
        instant_ref = find_ref(snap, ["radio", "Instant"])
        if instant_ref:
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
    type_text(tab, ref, PROMPTS["deepseek"], press_enter=False)
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
    for ref in reversed(button_refs[-3:]):
        try:
            click(tab, ref)
        except Exception:
            continue
        time.sleep(8)
        snap = snapshot(tab)
        if PROMPTS["deepseek"] not in snap or "paragraph:" in snap:
            reply = extract_reply(snap, PROMPTS["deepseek"])
            if "정상" in reply:
                return reply
    return wait_reply(tab, PROMPTS["deepseek"], timeout=45)


def main():
    results = {
        "chatgpt": run_chatgpt(),
        "gemini": run_gemini(),
        "deepseek": run_deepseek(),
    }
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
