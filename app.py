import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sarvamai import SarvamAI

KEY = os.environ.get("SARVAM_API_KEY", "").strip()
if not KEY:
    sys.exit("SARVAM_API_KEY is not set. Run: uv run --env-file .env uvicorn app:app")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_COOLDOWN = 90  # seconds to skip Gemini after a 429
_gemini_blocked_until = 0.0
_no_thinking = False  # flash-lite rejects thinkingConfig

client = SarvamAI(api_subscription_key=KEY)
app = FastAPI()
app.mount("/fonts", StaticFiles(directory="fonts"), name="fonts")

ROOMS = {
    "pitch": {
        "title": "Pitch in 20 seconds",
        "brief": "Explain what you are building to someone with no context. "
                 "Register: sharp, concrete, no jargon, no throat-clearing.",
        "success": "A stranger can repeat your point back after one hearing.",
        "persona": ("Ananya Rao", "an investor",
                    "skeptical but curious. Push on what it actually does and why anyone would pay for it."),
    },
    "salary": {
        "title": "Salary negotiation",
        "brief": "Ask for a raise. Register: firm and warm. "
                 "No apologies, no over-explaining, no justifying your existence.",
        "success": "The number is said once, clearly, and then you stop talking.",
        "persona": ("Meera Iyer", "your hiring manager",
                    "firm and budget-constrained. Hold at a lower number. Do not cave easily."),
        "numbers": ("The band for this role is 12 to 15 lakh. You opened at 12. You cannot exceed 15 without approvals."),
    },
    "doctor": {
        "title": "At the doctor",
        "brief": "Describe what is wrong so the doctor can act. "
                 "Register: plain, chronological, no self-diagnosis, no rambling history.",
        "success": "Symptom, duration, severity - in that order, in under 20 seconds.",
        "persona": ("Dr. Kulkarni", "a busy doctor",
                    "brisk and time-poor. Ask for specifics. Do not reassure the patient."),
    },
    "customer": {
        "title": "Angry customer",
        "brief": "A customer is shouting about a delayed order. Register: calm, ownership, "
                 "no blame, no policy recital.",
        "success": "They feel heard and know the next step before they hang up.",
        "persona": ("Rohit Sharma", "an angry customer",
                    "annoyed and escalating. Demand a concrete next step and a time."),
    },
    "auto": {
        "title": "Auto fare",
        "brief": "The meter says one thing, the driver says another. Register: friendly but "
                 "immovable. No shouting, no surrender.",
        "success": "You agree a number, and it is the meter or close to it.",
        "persona": ("Santosh", "an auto driver",
                    "wants a flat fare well above the meter. Cites traffic, return fare and CNG. "
                    "Haggles hard, but moves when you stay firm and specific."),
        "numbers": ("You opened at 500 rupees. Your floor is 380 rupees. You will not go below 380 for any reason."),
    },
    "landlord": {
        "title": "The landlord",
        "brief": "The geyser has been broken for a week. Register: warm, specific, on record. "
                 "No apology for asking.",
        "success": "A date, in writing, and who pays for the repair.",
        "persona": ("Mr. Deshpande", "your landlord",
                    "polite but stingy. Promises 'tomorrow' without committing, and hints that "
                    "repairs are your job."),
    },
    "office": {
        "title": "At the government counter",
        "brief": "Your certificate is stuck. Register: patient, precise, repetitive. "
                 "No anger, no begging.",
        "success": "You leave knowing the exact document and the exact counter.",
        "persona": ("Mrs. Shinde", "the clerk at the counter",
                    "bored and procedural. Asks for one more document without saying which, "
                    "and points at the notice board."),
    },
    "school": {
        "title": "Parent-teacher meeting",
        "brief": "Your child is falling behind in maths. Register: curious, not defensive. "
                 "Ask for one thing to do at home.",
        "success": "One specific thing to do this week, agreed with the teacher.",
        "persona": ("Mrs. Nair", "your child's class teacher",
                    "concerned but rushed. Wants to know what you will do at home, and has "
                    "ten other parents waiting."),
    },
}

SCRIPT = {
    "hi-IN": "Devanagari", "mr-IN": "Devanagari", "ne-IN": "Devanagari", "sa-IN": "Devanagari",
    "bn-IN": "Bengali", "as-IN": "Bengali", "ta-IN": "Tamil", "te-IN": "Telugu",
    "kn-IN": "Kannada", "gu-IN": "Gujarati", "pa-IN": "Gurmukhi", "od-IN": "Odia",
    "ml-IN": "Malayalam", "ur-IN": "Arabic", "en-IN": "Roman",
}

LANG_LABEL = {
    "hi-IN": "Hindi", "mr-IN": "Marathi", "bn-IN": "Bengali", "gu-IN": "Gujarati",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "od-IN": "Odia", "pa-IN": "Punjabi",
    "ta-IN": "Tamil", "te-IN": "Telugu", "en-IN": "Indian English",
}

# Two distinct voices so a conversation sounds like two people.
# (model, speaker) — v4-flash has per-language personas, v3 covers the rest.
COACH = {
    "hi-IN": ("bulbul:v4-flash", "sanchita_hi_feedback"),
    "mr-IN": ("bulbul:v4-flash", "ishita_mr_conversational"),
    "bn-IN": ("bulbul:v4-flash", "roopa_bn_conversational"),
    "gu-IN": ("bulbul:v4-flash", "pooja_gu_conversational"),
    "kn-IN": ("bulbul:v4-flash", "chaitra_kn_conversation"),
    "pa-IN": ("bulbul:v4-flash", "harpreet_pa_narration"),
    "ta-IN": ("bulbul:v4-flash", "gokul_ta_narration"),
    "te-IN": ("bulbul:v4-flash", "kavitha_te_conversation"),
    "en-IN": ("bulbul:v4-flash", "simran_en_conversation"),
    "ml-IN": ("bulbul:v3", "priya"),
    "od-IN": ("bulbul:v3", "priya"),
}
OTHER = {
    "hi-IN": ("bulbul:v4-flash", "aditya_hi_conversational"),
    "mr-IN": ("bulbul:v4-flash", "nilesh_mr_conversation"),
    "bn-IN": ("bulbul:v4-flash", "arnab_bn_conversation"),
    "gu-IN": ("bulbul:v4-flash", "bhavik_gu_conversation"),
    "kn-IN": ("bulbul:v4-flash", "chetan_kn_conversation"),
    "pa-IN": ("bulbul:v4-flash", "anand_pa_conversation"),
    "ta-IN": ("bulbul:v4-flash", "aravind_ta_ads"),
    "te-IN": ("bulbul:v4-flash", "tarun_te_narration"),
    "en-IN": ("bulbul:v4-flash", "dev_en_conversational"),
    "ml-IN": ("bulbul:v3", "shubh"),
    "od-IN": ("bulbul:v3", "shubh"),
}

FILLERS = [
    "um", "umm", "uh", "uhh", "hmm", "erm", "matlab", "yaani", "like",
    "you know", "i mean", "basically", "actually", "so yeah", "मतलब", "यानी", "उम",
]
HEDGES = [
    "maybe", "perhaps", "sort of", "kind of", "i think", "i guess", "i feel like",
    "i'm not sure", "im not sure", "just", "a bit", "somewhat", "probably",
    "shayad", "thoda", "zara", "शायद", "थोड़ा", "ज़रा",
]


def hits(terms, text):
    t = text.lower()
    n = 0
    for w in terms:
        if re.fullmatch(r"[a-z' ]+", w):
            n += len(re.findall(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t))
        else:
            n += t.count(w)
    return n


def score(wpm, fillers, hedges, point_at):
    s = 100.0
    s -= min(30, max(0, point_at - 3) * 2.5)
    s -= min(24, hedges * 4)
    s -= min(15, fillers * 2.5)
    if wpm:
        s -= min(8, max(0, abs(wpm - 140) - 25) * 0.25)
    return int(max(40, min(96, round(s))))


def transcribe(data, filename):
    r = client.speech_to_text.transcribe(
        file=(filename, data),
        model="saaras:v3",
        mode="codemix",
        language_code="unknown",
    )
    return (r.transcript or "").strip(), (r.language_code or "hi-IN")


def speak(text, lang, voices):
    if lang not in voices or not text:
        return None
    model, speaker = voices[lang]
    try:
        r = client.text_to_speech.convert(
            text=text[:900], language_code=lang, model=model,
            speaker=speaker, output_audio_codec="wav",
        )
        if r.audios:
            return "data:audio/wav;base64," + r.audios[0]
    except Exception as e:
        print("tts failed:", str(e)[:160])
    return None


def parse_json(raw):
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("no json")
    return json.loads(s[a:b + 1])


def ask(messages, max_tokens=700):
    r = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=messages,
        temperature=0.3,
        max_tokens=max_tokens,
    )
    return r.choices[0].message.content


def ask_json(messages, max_tokens=700):
    for _ in range(2):
        try:
            return parse_json(ask(messages, max_tokens))
        except Exception:
            messages = messages + [{
                "role": "user",
                "content": "Return only the JSON object. No prose, no code fences.",
            }]
    raise ValueError("model did not return json")


def scene_system(room, lang, history):
    name, role, trait = ROOMS[room]["persona"]
    label = LANG_LABEL.get(lang, "Hindi")
    mine = [t for r, t in history if r == "other" and t]
    turn = len([1 for r, _ in history if r == "other"]) + 1
    said = "\n".join(f"- {t}" for t in mine[-3:]) or "(none yet)"
    numbers = ROOMS[room].get("numbers")
    money = ""
    if numbers:
        quoted = []
        for t in mine:
            quoted += re.findall(r"\d[\d,]{1,5}", t)
        last = quoted[-1] if quoted else "none"
        money = (f"\n{numbers}"
                 f"\nThe last number you quoted was {last}. Your number only ever moves down, in small steps."
                 f" Never quote a number higher than one you have already said, even if they bid high.")
    return f"""You are {name}, {role}, in a live rehearsal of a real conversation. This is your line {turn}.
You are {trait}
Speak only {label} ({lang}), written in the {SCRIPT.get(lang, 'same')} script. Write the way people actually talk, including code-mixing if the other person does.
One or two short sentences, under 25 words, at most one question.
Never coach. Never evaluate. Never mention AI, rehearsal, or the exercise. Never break character.
Never repeat a line you have already used, and never greet again after the first line.
React to the specific thing they just said, then push the conversation forward.
Every turn must add something new: a new objection, a new condition, or a small concession. Do not raise the same objection twice.{money}
You have already said:
{said}"""


def sarvam_scene(room, lang, history):
    """Same character, written by Sarvam when Gemini is unavailable. Still contextual."""
    msgs = [{"role": "system", "content": scene_system(room, lang, history)}]
    for r, t in history:
        if t:
            msgs.append({"role": "assistant" if r == "other" else "user", "content": t})
    if not history:
        msgs.append({"role": "user", "content": "(The scene begins. You speak first.)"})
    line = ask(msgs, 200).strip().strip('"')
    if not line:
        raise RuntimeError("empty scene line")
    return line


def gemini_scene(room, lang, history):
    """One line from the other person. Gemini first, Sarvam second. No scripted lines."""
    global _gemini_blocked_until, _no_thinking
    if GEMINI_KEY and time.time() >= _gemini_blocked_until:
        contents = [{"role": "model" if r == "other" else "user", "parts": [{"text": t}]}
                    for r, t in history if t]
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "(The scene begins. You speak first.)"}]}]

        gen = {"temperature": 0.95}
        if not _no_thinking:
            gen["thinkingConfig"] = {"thinkingBudget": 0}
        body = {"systemInstruction": {"parts": [{"text": scene_system(room, lang, history)}]},
                "contents": contents,
                "generationConfig": gen}
        for attempt, wait in enumerate([0, 1.2]):
            if wait:
                time.sleep(wait)
            try:
                r = httpx.post(GEMINI_URL, params={"key": GEMINI_KEY}, json=body, timeout=30)
                if r.status_code == 400 and not _no_thinking:
                    _no_thinking = True
                    body["generationConfig"].pop("thinkingConfig", None)
                    print("gemini: retrying without thinkingConfig")
                    continue
                if r.status_code == 429:
                    _gemini_blocked_until = time.time() + GEMINI_COOLDOWN
                    print("gemini 429, backing off for", GEMINI_COOLDOWN, "s")
                    break
                r.raise_for_status()
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if text:
                    return text
            except Exception as e:
                code = getattr(getattr(e, "response", None), "status_code", "?")
                print("gemini failed:", code)
    return sarvam_scene(room, lang, history)


def wrong_script(out, lang):
    if lang == "en-IN":
        return False
    text = " ".join(str(n.get("text", "")) for n in out.get("notes", []))
    text += " " + str(out.get("rewrite", "")) + " " + str(out.get("steal", ""))
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 40:
        return False
    latin = sum(1 for c in letters if ord(c) < 128)
    return latin / len(letters) > 0.55


def metrics(transcript, duration):
    words = len(transcript.split())
    return {
        "words": words,
        "wpm": round(words / (duration / 60)) if duration > 1 and words else 0,
        "fillers": hits(FILLERS, transcript),
        "hedges": hits(HEDGES, transcript),
    }


def history_from(raw):
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []


@app.get("/")
def index():
    return FileResponse("index.html")


@app.post("/api/open")
async def open_scene(payload: dict):
    room = payload.get("room") if payload.get("room") in ROOMS else "pitch"
    lang = payload.get("lang") or "hi-IN"
    try:
        line = await asyncio.to_thread(gemini_scene, room, lang, [])
    except Exception as e:
        print("open failed:", str(e)[:160])
        return JSONResponse({"error": "The scene could not start. Try again."}, 502)
    audio = await asyncio.to_thread(speak, line, lang, OTHER)
    name, role, _ = ROOMS[room]["persona"]
    return {"line": line, "audio": audio, "name": name, "role": role, "lang": lang}


@app.post("/api/turn")
async def turn(room: str = Form(...), duration: float = Form(0), history: str = Form("[]"),
               file: UploadFile = File(...)):
    room = room if room in ROOMS else "pitch"
    data = await file.read()
    transcript, lang = await asyncio.to_thread(transcribe, data, file.filename or "take.webm")
    if not transcript:
        return JSONResponse({"error": "Kuch sunai nahi diya. Try again."}, 400)

    hist = history_from(history)
    said = next((h["text"] for h in reversed(hist) if h.get("role") == "other"), "")
    mine = [h for h in hist if h.get("role") == "you" and h.get("text")]
    prev = mine[-1] if mine else None
    label = LANG_LABEL.get(lang, "Hindi")
    m = metrics(transcript, duration)

    compare = ""
    if prev:
        compare = (f"\nTHEIR PREVIOUS ANSWER: {prev.get('text','')}"
                   f"\nIt scored {prev.get('score','?')}. Say what genuinely improved, quote their words.")

    sys_prompt = f"""You are a blunt but warm speaking coach in India. The speaker already speaks this language. You are NOT teaching language, grammar or vocabulary. You are coaching how they are heard.

ROOM: {ROOMS[room]['title']} - {ROOMS[room]['brief']}
SUCCESS LOOKS LIKE: {ROOMS[room]['success']}
THE OTHER PERSON JUST SAID: {said}{compare}

Rules:
- Reply with JSON only.
- Every text value in {label} ({lang}), in the same script as the transcript. If the speaker used Devanagari or another Indic script, your notes must use that script, not Roman letters. Never answer in English unless the transcript is English.
- notes: exactly 3, each under 20 words, specific to what they just said. No generic advice, no filler.
  1. kind "The point" - where THEIR point actually started, and what it was.
  2. kind "The words" - quote the weakest phrase THEY said and give the exact replacement. Always give a replacement. Never write that nothing needs improving.
  3. kind "The answer" - did THEY answer the person in the room, or talk past them.
- Write only about the speaker's own turn. Never summarise or describe what the other person said.
- rewrite: their answer rebuilt in 1-2 sentences, first person, natural spoken rhythm, same language and register.
- steal: one sentence worth memorising for this room.
- point_at: the second (0-30) when their core point first became clear. Use 30 if never.
- weak_phrases: exact phrases from the transcript that weakened them. Empty list if none.
- filler_phrases: exact fillers from the transcript. Empty list if none.
- improved: REQUIRED when a previous answer is given - up to 2 short lines on what genuinely got better, quoting their words. Empty list only if this is their first answer.
- still_working: one short line, or empty.
- verdict: under 10 words.

Shape: {{"point_at":0,"notes":[{{"kind":"","text":""}}],"rewrite":"","steal":"","verdict":"","weak_phrases":[],"filler_phrases":[],"improved":[],"still_working":""}}"""

    user = (f"TRANSCRIPT:\n{transcript}\n\n"
            f"Measured: {m['wpm']} words per minute, {m['fillers']} fillers, "
            f"{m['hedges']} hedges, {round(duration,1)}s long.")

    notes_task = asyncio.to_thread(ask_json, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user},
    ])
    other_task = asyncio.to_thread(gemini_scene, room, lang,
                                   [(h.get("role", "other"), h.get("text", "")) for h in hist]
                                   + [("you", transcript)])
    try:
        out, reply = await asyncio.gather(notes_task, other_task)
    except Exception as e:
        print("turn failed:", str(e)[:160])
        return JSONResponse({"error": "They didn't answer. Try that turn again."}, 502)

    if wrong_script(out, lang):
        strict = sys_prompt + (f"\n\nIMPORTANT: your previous answer was written in Roman/English script. "
                               f"Rewrite every string in {label}, using the {SCRIPT.get(lang, 'same')} script only.")
        try:
            out = ask_json([{"role": "system", "content": strict},
                            {"role": "user", "content": user}])
        except Exception as e:
            print("language retry failed:", str(e)[:120])

    point_at = int(out.get("point_at") or 30)
    m["hedges"] = max(m["hedges"], len(out.get("weak_phrases") or []))
    m["fillers"] = max(m["fillers"], len(out.get("filler_phrases") or []))

    rewrite_audio, reply_audio = await asyncio.gather(
        asyncio.to_thread(speak, out.get("rewrite", ""), lang, COACH),
        asyncio.to_thread(speak, reply, lang, OTHER),
    )

    return {
        "transcript": transcript,
        "lang": lang,
        "langLabel": label,
        "duration": round(duration, 1),
        **m,
        "point_at": point_at,
        "score": score(m["wpm"], m["fillers"], m["hedges"], point_at),
        "notes": out.get("notes", [])[:3],
        "rewrite": out.get("rewrite", ""),
        "steal": out.get("steal", ""),
        "verdict": out.get("verdict", ""),
        "improved": out.get("improved", [])[:2],
        "still_working": out.get("still_working", ""),
        "audio": rewrite_audio,
        "counterpart": reply,
        "counterpart_audio": reply_audio,
        "review_at": (datetime.now() + timedelta(days=3)).strftime("%d %b"),
    }
