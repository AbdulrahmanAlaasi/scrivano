# Sard · Launch Marketing Kit

## LinkedIn post (English, primary)

---

I kept leaving meetings with two bad options: pay attention and lose the notes, or take notes and lose the meeting.

So I built Sard (سرد, Arabic for "narration").

Sard is an AI meeting notetaker with one unusual principle: it is private by architecture, not by promise.

🎙️ Transcription runs inside your browser with Whisper. The audio never leaves your machine.
🤖 The AI notes are written by your own local model (Ollama, LM Studio, Jan). No API keys, no cloud.
🧾 Every summary, decision, and task links back to the exact second it was said. If the meeting did not say it, Sard does not claim it. Owners and deadlines are never invented.
💬 Ask any meeting a question. If the answer is not in the transcript, Sard says so instead of guessing.
🧠 For teams: meetings become approved organizational memory. The AI suggests facts, you approve or reject them, conflicts surface as cards, and history is versioned. Nothing is silently overwritten.

The local app is free forever, no account needed. The team backend is open source and self-hostable, with a managed cloud in founding access.

Try it in your browser right now: https://sard.alaasi.dev
Code and docs: https://github.com/AbdulrahmanAlaasi/sard

Built solo: TypeScript + Vite on the front, Django + Supabase (pgvector) on the back, 113 automated tests, with strict per-meeting retrieval isolation that the test suite proves.

If your team cannot send meeting audio to a US cloud, I would especially love to talk.

#buildinpublic #ai #privacy #meetings #opensource #selfhosted #localfirst

---

## LinkedIn post (Arabic, follow-up a few days later)

---

سرد: ملاحظات اجتماعات بالذكاء الاصطناعي، من غير ما يطلع الصوت من جهازك.

التفريغ يعمل داخل المتصفح، والنموذج اللغوي يعمل على جهازك، وكل جملة في الملخص مرتبطة باللحظة اللي انقالت فيها. إذا الاجتماع ما قالها، سرد ما يدّعيها.

مجاني للاستخدام الفردي، ومفتوح المصدر للفرق.

https://sard.alaasi.dev

---

## Visuals: 6 screenshots (1200×750, paper background, saffron accents)

1. **Hero shot:** landing page top fold (logo + "Meeting notes that narrate themselves").
2. **Capture screen:** the four capture cards (mic, tab, upload, paste), shows breadth.
3. **Notes with receipts:** a finished meeting, AI Notes tab, action items with owner
   pills visible; circle one citation timestamp in saffron.
4. **Meeting Chat honesty:** side-by-side of a cited answer and the "not in the
   transcript" answer. This is the differentiator shot.
5. **Memory review:** pending suggestion + conflict card (keep / replace / keep both).
6. **Proof shot:** terminal with `113 passed` test output over the architecture
   diagram. Speaks to engineers and hiring managers.

Carousel order for LinkedIn: 1, 4, 3, 5, 2, 6. Add a one-line caption on each image
in Fraunces, ink on paper.

## Video: 45-second screen recording (no talking-head needed)

Storyboard, one continuous take with cuts, captions burned in (Inter, bottom third):

| t | Shot | Caption |
|---|---|---|
| 0-5s | Landing hero scrolls | "Meetings deserve a narrator." |
| 5-12s | Click Record microphone, speak two sentences about a fake project deadline | "Transcribed in your browser. Audio never leaves." |
| 12-20s | Transcript appears with timestamps, click Generate notes | "Your local AI writes the story." |
| 20-30s | Notes appear; hover an action item and a decision | "Every claim has a receipt. Owners are never invented." |
| 30-38s | Meeting Chat: ask "What is the deadline?", cited answer appears; ask something absent, honest not-found appears | "It refuses to guess." |
| 38-45s | Landing pricing, end card: logo + سرد + URL | "Free. Local. sard.alaasi.dev" |

Record at 1080p in a clean browser profile, light OS theme, cursor smoothing on
(Screen Studio or Cursorful). Export a 4:5 crop for LinkedIn feed and 16:9 for the
README/YouTube.

## Distribution checklist

- LinkedIn (EN post + carousel + video), tag nothing, reply to every comment for 2h.
- Product Hunt draft using the same 6 screenshots ("Sard: private AI meeting notes").
- r/selfhosted + r/LocalLLaMA: lead with the self-host backend, not the SaaS.
- Arabic dev Twitter/X thread with the Arabic post.
- Personal site alaasi.dev: case-study writeup "How I isolation-test a RAG system".
