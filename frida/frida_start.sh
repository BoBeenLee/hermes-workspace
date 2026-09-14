#!/system/bin/sh
SP=$(pidof system_server)
for kv in $(tr "\0" "\n" < /proc/$SP/environ); do
  case "$kv" in ANDROID_SOCKET_*) ;; *=*) export "$kv";; esac
done
exec /data/local/tmp/frida-server -l 0.0.0.0:27042 -P -C --policy-softener=internal
