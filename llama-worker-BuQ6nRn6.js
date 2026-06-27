"use strict";
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="3e1c884e-940d-517a-9c55-55fd4584e5ed")}catch(e){}}();

var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
let nodeLlamaCpp = null;
let llama = null;
let model = null;
let context = null;
let session = null;
let currentStatus = "idle";
const activeAbortControllers = /* @__PURE__ */ new Map();
function sendMessage(message) {
  process.parentPort?.postMessage(message);
}
function updateStatus(status, error) {
  currentStatus = status;
  sendMessage({ type: "status", status, error });
}
async function loadNodeLlamaCpp() {
  if (!nodeLlamaCpp) {
    nodeLlamaCpp = await import("node-llama-cpp");
  }
  return nodeLlamaCpp;
}
async function initModel(modelPath, contextSize = 32768, gpuLayers) {
  if (model) {
    console.log("[LlamaWorker] Model already loaded, disposing first");
    await dispose();
  }
  updateStatus("loading");
  try {
    console.log("[LlamaWorker] Loading node-llama-cpp module...");
    const llamaCpp = await loadNodeLlamaCpp();
    console.log("[LlamaWorker] Initializing llama...");
    llama = await llamaCpp.getLlama();
    console.log("[LlamaWorker] Loading model from:", modelPath);
    model = await llama.loadModel({
      modelPath,
      gpuLayers
    });
    console.log("[LlamaWorker] Creating context with size:", contextSize);
    context = await model.createContext({
      contextSize
    });
    session = new llamaCpp.LlamaChatSession({
      contextSequence: context.getSequence()
    });
    console.log("[LlamaWorker] Model loaded successfully");
    updateStatus("ready");
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error("[LlamaWorker] Failed to load model:", errorMessage);
    updateStatus("error", errorMessage);
    throw error;
  }
}
async function runCompletion(requestId, options) {
  if (!session || !model) {
    sendMessage({
      type: "error",
      requestId,
      error: "Model not initialized"
    });
    return;
  }
  updateStatus("generating");
  const abortController = new AbortController();
  activeAbortControllers.set(requestId, abortController);
  try {
    const systemMessage = options.messages.find((m) => m.role === "system");
    const userMessages = options.messages.filter((m) => m.role !== "system");
    if (systemMessage) {
      session.setChatHistory([{ type: "system", text: systemMessage.content }]);
    }
    const lastUserMessage = userMessages[userMessages.length - 1];
    if (!lastUserMessage || lastUserMessage.role !== "user") {
      throw new Error("Last message must be from user");
    }
    const response = await session.prompt(lastUserMessage.content, {
      temperature: options.temperature,
      maxTokens: options.maxTokens ?? 2048,
      signal: abortController.signal,
      stopOnAbortSignal: true,
      onTextChunk(chunk) {
        sendMessage({
          type: "chunk",
          requestId,
          content: chunk
        });
      }
    });
    activeAbortControllers.delete(requestId);
    sendMessage({
      type: "done",
      requestId,
      fullResponse: response
    });
    updateStatus("ready");
  } catch (error) {
    activeAbortControllers.delete(requestId);
    const err = error;
    if (err.name === "AbortError" || abortController.signal.aborted) {
      console.log("[LlamaWorker] Request aborted:", requestId);
      sendMessage({
        type: "done",
        requestId,
        fullResponse: ""
      });
      updateStatus("ready");
      return;
    }
    const errorMessage = err.message || String(error);
    console.error("[LlamaWorker] Completion error:", errorMessage);
    sendMessage({
      type: "error",
      requestId,
      error: errorMessage
    });
    updateStatus("ready");
  }
}
function abortRequest(requestId) {
  const controller = activeAbortControllers.get(requestId);
  if (controller) {
    console.log("[LlamaWorker] Aborting request:", requestId);
    controller.abort();
    activeAbortControllers.delete(requestId);
  }
}
async function dispose() {
  console.log("[LlamaWorker] Disposing resources");
  for (const [requestId, controller] of activeAbortControllers) {
    console.log("[LlamaWorker] Aborting active request:", requestId);
    controller.abort();
  }
  activeAbortControllers.clear();
  if (session) {
    session = null;
  }
  if (context) {
    await context.dispose();
    context = null;
  }
  if (model) {
    await model.dispose();
    model = null;
  }
  llama = null;
  currentStatus = "idle";
}
process.parentPort?.on("message", async (event) => {
  const message = event.data;
  try {
    switch (message.type) {
      case "init":
        await initModel(
          message.modelPath,
          message.contextSize,
          message.gpuLayers
        );
        break;
      case "completion":
        await runCompletion(message.requestId, message.options);
        break;
      case "abort":
        abortRequest(message.requestId);
        break;
      case "dispose":
        await dispose();
        updateStatus("idle");
        break;
      case "getStatus":
        sendMessage({
          type: "status",
          status: currentStatus
        });
        break;
      default:
        console.warn(
          "[LlamaWorker] Unknown message type:",
          message.type
        );
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error("[LlamaWorker] Worker message handler error:", error);
    sendMessage({
      type: "error",
      error: errorMessage
    });
  }
});
sendMessage({ type: "ready" });
console.log("[LlamaWorker] Worker started");
//# sourceMappingURL=llama-worker-BuQ6nRn6.js.map

//# debugId=3e1c884e-940d-517a-9c55-55fd4584e5ed
