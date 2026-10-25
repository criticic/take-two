# Take Two

**We don't fix your language. We fix your point.**

A rehearsal room for the conversations that decide things — in the language you actually have them in. Someone talks back, you answer, and the notes land in the margin beside the line they're about. Then you keep going.

Not a language course. No lessons, no levels, no vocabulary drills.

## Run

```bash
uv run --env-file .env uvicorn app:app --port 8000
```

Open http://localhost:8000

`.env` needs both keys:

```
SARVAM_API_KEY=...
GEMINI_API_KEY=...
```

## Rooms

| Room | Who's across the table | What you're trying to get |
|---|---|---|
| Pitch in 20 seconds | Ananya Rao, investor | A stranger can repeat your point |
| Salary negotiation | Meera Iyer, hiring manager | The number, said once, without apology |
| At the doctor | Dr. Kulkarni | Symptom, duration, severity |
| Angry customer | Rohit Sharma | A next step and a time |
| Auto fare | Santosh, auto driver | The meter, or close to it |
| The landlord | Mr. Deshpande | A date, in writing |
| At the government counter | Mrs. Shinde | The exact document and counter |
| Parent–teacher meeting | Mrs. Nair | One thing to do this week |

Eleven languages: Hindi, Marathi, Bengali, Tamil, Telugu, Kannada, Gujarati, Punjabi, Odia, Malayalam, English. The opener language is a hint — after your first line it follows what you actually speak.

## How a turn works

1. They speak first, in their voice. You get context before you open your mouth.
2. The moment their line ends, the mic opens by itself. You just talk — it closes after ~1.3s of silence and sends. No button, no timer to watch.
3. You answer. 30 seconds max, no interruptions.
4. Their reply and your notes arrive **together**: three notes and a rewritten line in the margin, beside your words.
5. Repeat. Every turn gets its own margin. The conversation remembers everything said before it.
6. End the scene whenever — you get the score arc and one line to keep.

## Stack

| Job | Who |
|---|---|
| Listen | Sarvam `saaras:v3`, `mode=codemix`, auto language detect |
| Coach | Sarvam `sarvam-105b-conversations` — notes, rewrite, verdict |
| Speak (coach) | Sarvam `bulbul:v4-flash` personas, `bulbul:v3` for Malayalam/Odia |
| Speak (the other person) | Sarvam, a different voice per language |
| The other person | Gemini `gemini-3.5-flash-lite`, full session history, anchored numbers |

Sarvam owns everything Indic: hearing, judgement, and both voices. Gemini writes the opposition.

**No scripted dialogue.** If Gemini rate-limits, the same character is written by Sarvam 105B with the same context, and Gemini is skipped for 90s so turns stay fast. No canned lines.

**Negotiation rooms have numbers.** Santosh opens at 500 with a floor of 380, and his price only ever moves down — the prompt carries his last quoted number, so he cannot re-raise an offer he already made.

## Design

The screen is a rehearsal script, not a dashboard. Character names in the left gutter, dialogue in a measured column, notes in the right margin — in pencil, not in cards. One dark object on the page: the slate that starts a take.

- **Paper** `#E9E7DE`, **ink** `#16181A`, **pencil** `#2C4A6B` for observation, **red** `#B23F2C` for change.
- **Tiro Devanagari Hindi** carries what you said. **Mukta** carries what the machine noticed.
- Fonts are self-hosted in `fonts/` — no venue wifi.
- One motion: the notes write themselves in. The clapper snaps shut on record.

## Known limits

- **Gemini free tier rate-limits (429).** Three attempts with backoff, then Sarvam takes over the character. Don't rehearse twenty turns right before demoing.
- **TTS covers 10 Indian languages + English.** Notes still render for others; audio disables.
- **A turn is ~5–8s.** STT + notes + two voice calls, in parallel where possible.
- **No barge-in.** Turn-taking is scripted on purpose; open-ended chat is where live demos die.
- **Auto-listen needs a one-time mic grant.** Turn it off from the topbar if the room is noisy.

## Fallbacks

- No mic → "use a recording" file input.
- No network → `/?demo=notes` and `/?demo=delta` replay a recorded session.
