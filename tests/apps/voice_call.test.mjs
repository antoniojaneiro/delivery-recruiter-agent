// Runs sazon/voice_call.js with a fake SDK, microphone and page, and prints one JSON line per case: what the page showed and did.
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const { startCall } = await import(pathToFileURL(resolve(process.argv[2])).href);
const words = { listening: "L", speaking: "S", ended: "E", error: "X", mic: "M" };
const base = { words, session: "sess_1", signedUrl: "wss://x", opening: "Hola", language: "es" };

async function run(name, { call = base, mic, session = async () => {}, click } = {}) {
  const clicks = [];
  const status = { textContent: "C" };
  let options;
  const Conversation = { startSession: async (o) => { options = o; await session(o); } };
  const parent = { document: { querySelector: (selector) => {
    if (click === "throws") throw new Error("cross-origin");
    return click === "none" ? null : { click: () => clicks.push(selector) };
  } } };
  await startCall(call, { Conversation, status, mic: mic ?? { getUserMedia: async () => {} }, parent });
  const result = { name, status: status.textContent, clicks, options: options && JSON.parse(JSON.stringify(options)) };
  if (options) {
    options.onModeChange({ mode: "speaking" }); result.speaking = status.textContent;
    options.onModeChange({ mode: "listening" }); result.listening = status.textContent;
    for (const reason of ["agent", "user", "error"]) {
      clicks.length = 0;
      options.onDisconnect({ reason }); result["end_" + reason] = [status.textContent, clicks.length];
    }
    options.onDisconnect("closed"); result.end_text = status.textContent;
    options.onError({ message: "boom" }); result.error = status.textContent;
  }
  console.log(JSON.stringify(result));
}

await run("started");
await run("no_language", { call: { ...base, language: null } });
await run("mic_refused", { mic: { getUserMedia: async () => { const e = new Error("no"); e.name = "NotAllowedError"; throw e; } } });
await run("other_failure", { session: async () => { throw new Error("socket"); } });
await run("page_unreachable", { click: "throws" });
await run("no_button", { click: "none" });
