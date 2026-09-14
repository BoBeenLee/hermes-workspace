package com.bbl.iristhread;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage.LoadPackageParam;

/**
 * Put a KakaoTalk photo/file into the same 댓글(thread) as its caption, for the Iris bot.
 *
 * <p>Iris can thread a text reply ({@code /reply threadId=...} -> chat_logs.thread_id) but
 * NOT a media row: KakaoTalk's share path builds {@code ChatSendingLog.b(id, mediaType,
 * scope=0, threadId=null, ...)} with those two literal, and there is no external surface to
 * change them. This module rewrites those two constructor args when our bot has just sent a
 * media row it wants threaded. The daemon signals which thread via a hint file
 * ({@code iris_client.write_thread_hint}); nothing else is touched.
 *
 * <p><b>Why the constructor, by position, not by name:</b> the class name
 * {@code com.kakao.talk.manager.send.sending.ChatSendingLog$b} is not obfuscated and its
 * constructor has no name to obfuscate. The message-type enum ({@code cu8}) is obfuscated but
 * its constant NAMES survive R8 ({@code Photo}/{@code File}/...), so we match on those. And in
 * every ChatSendingLog.b constructor the layout is (chatRoomId, type, int scope, Long
 * threadId, ...) - scope and threadId sit immediately after the type enum. So we depend only
 * on: the stable class name, the R8-preserved enum names, and that arg order. No obfuscated
 * field or setter name is referenced. Re-verify the arg order with baksmali on a KakaoTalk
 * upgrade (see android/iris-thread-hook/README.md); measured against 26.7.2.
 */
public class IrisThreadHook implements IXposedHookLoadPackage {

    private static final String PKG = "com.kakao.talk";
    private static final String BUILDER = "com.kakao.talk.manager.send.sending.ChatSendingLog$b";
    private static final String HINT_PREFIX = "/data/local/tmp/iris_thread_";
    // A hint older than this is stale - a manual photo, or a leftover from a past send. The
    // bot serialises sends per room, so a fresh hint belongs to the send happening now.
    private static final long TTL_MS = 60_000L;
    // scope 2 = 댓글에만, 3 = 대화방+댓글 (Iris#112). Match the text caption; validate 2 vs 3 in
    // the Part A E2E and flip if the photo does not land where the caption did.
    private static final int SCOPE_THREAD = 2;
    // Enum constant names R8 keeps. These are the media rows our bot actually emits.
    private static final Set<String> MEDIA = new HashSet<>(Arrays.asList(
            "Photo", "MultiPhoto", "Video", "LargeVideo", "File", "LargeFile"));

    @Override
    public void handleLoadPackage(LoadPackageParam lpp) {
        if (!PKG.equals(lpp.packageName)) {
            return;
        }
        final Class<?> builder;
        try {
            builder = XposedHelpers.findClass(BUILDER, lpp.classLoader);
        } catch (Throwable t) {
            XposedBridge.log("iris-thread: builder class not found (kakao update?): " + t);
            return;
        }
        XposedBridge.hookAllConstructors(builder, new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                try {
                    inject(param.args);
                } catch (Throwable t) {
                    // Never let a hook error break a send.
                    XposedBridge.log("iris-thread: inject error " + t);
                }
            }
        });
        XposedBridge.log("iris-thread: armed on " + BUILDER);
    }

    /** Rewrite scope+threadId in place when this is a media build our bot has flagged. */
    private static void inject(Object[] args) {
        if (args == null || args.length < 3) {
            return;
        }
        int typeIdx = -1;
        for (int i = 0; i < args.length; i++) {
            if (args[i] instanceof Enum && MEDIA.contains(((Enum<?>) args[i]).name())) {
                typeIdx = i;
                break;
            }
        }
        if (typeIdx < 0) {
            return;                        // not a media row
        }
        // The media path always passes a primitive chatRoomId (boxed here) as arg0. The other
        // constructor takes a chatroom OBJECT first - that is the text path; skip it.
        if (!(args[0] instanceof Long)) {
            return;
        }
        int scopeIdx = typeIdx + 1;
        int threadIdx = typeIdx + 2;
        if (threadIdx >= args.length || !(args[scopeIdx] instanceof Integer)) {
            return;                        // arg layout drifted - re-pin (see README)
        }
        long chatId = (Long) args[0];
        Long threadId = readHint(chatId);
        if (threadId == null) {
            return;                        // no fresh hint: leave it a loose row
        }
        args[scopeIdx] = Integer.valueOf(SCOPE_THREAD);
        args[threadIdx] = threadId;
        XposedBridge.log("iris-thread: " + ((Enum<?>) args[typeIdx]).name()
                + " chat " + chatId + " -> thread " + threadId);
    }

    /** The thread root the daemon left for this chat, or null when there is none / it is stale. */
    private static Long readHint(long chatId) {
        File f = new File(HINT_PREFIX + chatId);
        if (!f.exists() || System.currentTimeMillis() - f.lastModified() > TTL_MS) {
            return null;
        }
        try (BufferedReader r = new BufferedReader(new FileReader(f))) {
            String line = r.readLine();
            return line == null ? null : Long.valueOf(line.trim());
        } catch (Throwable t) {
            return null;
        }
    }
}
