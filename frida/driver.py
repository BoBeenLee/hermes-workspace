#!/usr/bin/env python3
"""Keep the KakaoTalk media->댓글 Frida hook attached, self-healing across restarts.

Runs on the DGX host (not in the container) under systemd (kakao-frida-hook.service). It
connects to frida-server inside the redroid container, attaches to com.kakao.talk, and
loads iris_thread.js. Two things it must survive:

  * KakaoTalk restarting - re-attach when the session detaches.
  * The container restarting - frida-server dies with it (it is not an installed service),
    so ensure it is up (relaunching it via docker exec + frida_start.sh) before attaching.

Why frida at all: LSPosed/Zygisk cannot inject zygote in redroid (no boot ramdisk, so
magiskinit never hooks zygote - verified). Frida ptrace-attaches the running app instead,
needing no Magisk, no resign, and no container recreate. See knowledge/runbooks/iris-on-dgx.md.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

CONTAINER = os.environ.get("IRIS_CONTAINER", "redroid-poc")
ADDR = os.environ.get("FRIDA_ADDR", "172.17.0.2:27042")
APP = "com.kakao.talk"
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(HERE, "iris_thread.js")
# frida_start.sh imports system_server's env (BOOTCLASSPATH etc.) - frida-server creates a
# JavaVM at startup and aborts without it - then execs frida-server -l 0.0.0.0:27042.
FRIDA_START = "/data/local/tmp/frida_start.sh"


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def frida_server_up() -> bool:
    r = subprocess.run(["docker", "exec", CONTAINER, "/system/bin/sh", "-c", "pidof frida-server"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return bool(r.stdout.strip())


def ensure_frida_server() -> None:
    if frida_server_up():
        return
    log("frida-server down; relaunching")
    subprocess.run(["docker", "exec", "-d", CONTAINER, "/system/bin/sh", "-c",
                    f"setsid sh {FRIDA_START} >/data/local/tmp/frida.log 2>&1 </dev/null"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)


def main() -> None:
    import frida  # noqa: E402 - imported here so the module loads even if frida is missing

    script_src = open(SCRIPT_PATH, encoding="utf-8").read()
    dev = None
    while True:
        try:
            ensure_frida_server()
            if dev is None:
                dev = frida.get_device_manager().add_remote_device(ADDR)
            apps = [a for a in dev.enumerate_applications() if a.identifier == APP]
            if not apps:
                log(f"{APP} not running; waiting")
                time.sleep(3)
                continue
            session = dev.attach(apps[0].pid)
            script = session.create_script(script_src)
            script.on("message", lambda m, d: log(
                m.get("payload") if m.get("type") == "send" else f"script-error {m}"))
            script.load()
            log(f"attached pid {apps[0].pid}")
            gone = threading.Event()
            session.on("detached", lambda reason, *a: (log(f"detached: {reason}"), gone.set()))
            gone.wait()
        except Exception as exc:  # noqa: BLE001 - a chat hook must keep trying, never exit
            log(f"reconnect after error: {exc}")
            dev = None  # force a fresh remote device (frida-server may have restarted)
            time.sleep(3)


if __name__ == "__main__":
    main()
