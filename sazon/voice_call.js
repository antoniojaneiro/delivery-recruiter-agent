// The browser side of a live voice call (D93, D94): ask for the microphone, start the ElevenLabs conversation with the signed
// address our server asked for, and show whether Sofía is listening or speaking. sazon/voice_component.py puts this file in the
// page next to the SDK import and a JSON `call` (the values are data, never code); tests/apps/test_voice_call_js.py runs it in Node
// with a fake SDK, microphone and page.
//
// call: { words, session, signedUrl, opening, language }       env: { Conversation, status, mic, parent }

// What ElevenLabs says when a call ends or fails, shown so a refusal is not mistaken for a hang-up.
const reason = (info) => {
  const text = typeof info === "string" ? info : (info && (info.reason || info.message)) || "";
  return text ? " (" + String(text).slice(0, 200) + ")" : "";
};

// A call that ended by itself (or by the candidate) is closed on the page too: its button and note go. An error is left on screen.
const closeOnPage = (parent) => {
  try {
    const button = parent.document.querySelector(".st-key-voice_end button");
    if (button) button.click();
  } catch (error) { /* the page cannot be reached from here: the chat page closes the call itself a little later */ }
};

export async function startCall(call, env) {
  const { words, session, signedUrl, opening, language } = call;
  const { Conversation, status, mic, parent } = env;
  try {
    await mic.getUserMedia({ audio: true });
    await Conversation.startSession({
      signedUrl,
      dynamicVariables: { voice_session: session, opening },
      ...(language ? { overrides: { agent: { language } } } : {}),
      onModeChange: (change) => { status.textContent = change.mode === "speaking" ? words.speaking : words.listening; },
      onDisconnect: (details) => {
        status.textContent = words.ended + reason(details);
        if (details && (details.reason === "agent" || details.reason === "user")) closeOnPage(parent);
      },
      onError: (message) => { status.textContent = words.error + reason(message); },
    });
    status.textContent = words.listening;
  } catch (error) {
    status.textContent = (error && error.name === "NotAllowedError") ? words.mic : words.error;
  }
}
