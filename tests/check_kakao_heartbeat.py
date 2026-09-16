"""Fails if the heartbeat schedule drifts from the documented cadence."""
import sys
sys.path.insert(0, "/home/bobeenlee/.hermes/kakao-ai-chat")
import kakao_ai_chat as k

assert k.HEARTBEAT_SECONDS == 60, k.HEARTBEAT_SECONDS

t, interval, beats = k.HEARTBEAT_SECONDS, float(k.HEARTBEAT_SECONDS), []
while t <= k.TURN_HARD_CAP_SECONDS:
    beats.append(round(t / 60, 1))
    interval = k.next_beat(interval)
    t += interval

# First sign of life must land inside a minute: TURN_START_NOTE is gone.
assert beats[0] <= 1.0, beats[0]
# Backoff must actually back off, or a wedged turn spams the room.
assert all(b < a for b, a in zip(beats, beats[1:])) and len(beats) <= 8, beats
print("OK — beats at %s min (%d inside the %d min cap)"
      % (", ".join(str(b) for b in beats), len(beats), k.TURN_HARD_CAP_SECONDS // 60))
