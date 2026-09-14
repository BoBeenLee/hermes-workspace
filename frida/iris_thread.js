'use strict';
Java.perform(function () {
  var TTL = 60000;
  var PENDING = '/data/local/tmp/iris_thread_pending';
  var MEDIA = ['Photo', 'MultiPhoto', 'Video', 'LargeVideo', 'File', 'LargeFile'];
  var Builder = Java.use('com.kakao.talk.manager.send.sending.ChatSendingLog$b');
  var JLong = Java.use('java.lang.Long');
  var JFile = Java.use('java.io.File');
  var FileReader = Java.use('java.io.FileReader');
  var BufferedReader = Java.use('java.io.BufferedReader');

  // Consume-once WITHOUT deleting: the hook runs as uid 10087 (kakao) and cannot delete
  // a root-owned file in /data/local/tmp (dir 771). Instead remember the mtime we last
  // used; a fresh hint has a newer mtime. The daemon rewrites the file per send.
  var lastConsumed = 0;

  function readPending() {
    try {
      var f = JFile.$new(PENDING);
      if (!f.exists()) return null;
      var mtime = f.lastModified().valueOf();
      if ((new Date()).getTime() - mtime > TTL) return null;   // stale
      if (mtime <= lastConsumed) return null;                  // already used this one
      var br = BufferedReader.$new(FileReader.$new(f));
      var line = br.readLine(); br.close();
      if (line === null) return null;
      line = line.trim();
      if (!line.length) return null;
      lastConsumed = mtime;
      return line;
    } catch (e) { return null; }
  }

  var armed = 0;
  Builder.$init.overloads.forEach(function (ov) {
    var at = ov.argumentTypes;
    if (!(at.length === 5 && at[0].className === 'long' && at[2].className === 'int'
          && at[3].className === 'java.lang.Long' && at[4].className === 'boolean')) return;
    var cu8 = at[1].className;
    var orig = Builder.$init.overload('long', cu8, 'int', 'java.lang.Long', 'boolean');
    orig.implementation = function (a0, a1, a2, a3, a4) {
      try {
        var name = (a1 !== null) ? a1.name() : null;
        if (name !== null && MEDIA.indexOf(name) >= 0) {
          var hint = readPending();
          if (hint !== null) {
            send('iris-thread: ' + name + ' -> thread ' + hint);
            // scope 3 = 방+스레드: the media shows in the main timeline AND is linked
            // as a 댓글. scope 2 (스레드에만) hid it from the main chat -> looked missing.
            return orig.call(this, a0, a1, 3, JLong.$new(hint), a4);
          }
        }
      } catch (e) { send('iris-thread ERR ' + e); }
      return orig.call(this, a0, a1, a2, a3, a4);
    };
    armed++;
  });
  send('iris-thread: armed on ' + armed + ' ctor(s)');
});
