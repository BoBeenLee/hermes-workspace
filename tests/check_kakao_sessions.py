"""Smallest check that fails if the session TTL / thread-scoping logic breaks.

Run on the DGX host against the DEPLOYED daemon:
    ~/.hermes/hermes-agent/venv/bin/python check_kakao_sessions.py
"""
import json, sys, time
sys.path.insert(0, "/home/bobeenlee/.hermes/kakao-ai-chat")
import kakao_ai_chat as k

CHAT = 999999999999
THREAD = 777777777777

# --- scoping: a room key and a thread key are different files -----------------
room = k.session_path(CHAT)
thread = k.session_path(CHAT, THREAD)
assert room != thread, "thread turn must not share the room's session file"
assert thread.name == f"{CHAT}-{THREAD}.json", thread.name
# falsy thread ids mean "top level", not a literal 0
assert k.session_path(CHAT, 0) == room, "thread_id 0 must fall back to the room"
assert k.session_path(CHAT, None) == room

# --- fresh load ---------------------------------------------------------------
k.save_session_id(CHAT, "sess_room")
k.save_session_id(CHAT, "sess_thread", THREAD)
assert k.load_session_id(CHAT) == "sess_room"
assert k.load_session_id(CHAT, THREAD) == "sess_thread", "thread must resume its own session"

# --- TTL expiry, per file -----------------------------------------------------
stale = json.dumps({"session_id": "sess_stale",
                    "updated_at": time.time() - k.SESSION_TTL_SECONDS - 60})
thread.write_text(stale, "utf-8")
assert k.load_session_id(CHAT, THREAD) == "", "stale thread session must return empty"
assert not thread.exists(), "stale file must be unlinked"
assert k.load_session_id(CHAT) == "sess_room", "expiring a thread must not touch the room"

# --- reset drops the room AND its threads -------------------------------------
k.save_session_id(CHAT, "sess_thread2", THREAD)
assert k.reset_sessions(CHAT) == 2, "reset must drop the room file and its thread files"
assert k.load_session_id(CHAT) == "" and k.load_session_id(CHAT, THREAD) == ""

# --- degenerate inputs do not crash -------------------------------------------
assert k.load_session_id(0) == ""
k.save_session_id(0, "x")
assert k.reset_sessions(CHAT) == 0

print("OK — TTL=%.0fh, room/thread scoping, per-file expiry, room-wide reset"
      % (k.SESSION_TTL_SECONDS / 3600))
