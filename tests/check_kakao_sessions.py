"""Smallest check that fails if the TTL/reset logic breaks."""
import json, sys, time
sys.path.insert(0, "/home/bobeenlee/.hermes/kakao-ai-chat")
import kakao_ai_chat as k

CHAT = 999999999999
p = k.session_path(CHAT)

# fresh -> returned
k.save_session_id(CHAT, "sess_fresh")
assert k.load_session_id(CHAT) == "sess_fresh", "fresh session should load"

# stale -> dropped, empty
p.write_text(json.dumps({"session_id": "sess_stale",
                         "updated_at": time.time() - k.SESSION_TTL_SECONDS - 60}), "utf-8")
assert k.load_session_id(CHAT) == "", "stale session must return empty"
assert not p.exists(), "stale session file must be unlinked"

# reset drops it
k.save_session_id(CHAT, "sess_again")
assert k.reset_sessions(CHAT) == 1, "reset_sessions should drop exactly one"
assert k.load_session_id(CHAT) == "", "after reset, nothing to resume"

# no chat_id -> no crash
assert k.load_session_id(0) == ""
k.save_session_id(0, "x")

print("TTL/reset checks passed (TTL=%.0fh)" % (k.SESSION_TTL_SECONDS / 3600))
