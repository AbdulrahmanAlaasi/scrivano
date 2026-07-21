# Sard · Launch Marketing Kit

Sard is free, open source, and 100% local. There is nothing to sell in these posts:
the goal is reach, GitHub stars, and reputation.

## LinkedIn post (English, primary)

---

I kept leaving meetings with two bad options: pay attention and lose the notes, or take notes and lose the meeting.

So I built Sard (سرد, Arabic for "narration").

Sard is an AI meeting notetaker with one unusual property: it runs entirely on your machine.

🎙️ Transcription happens inside your browser with Whisper. The audio never leaves your computer.
🤖 The notes are written by your own local model (Ollama, LM Studio, Jan, llamafile). No API keys, no cloud, no account.
🧾 Summary, key points, decisions, and action items in a clean layout. Owners and due dates are captured when they were said, never invented.
🖥️ Record your mic, record a Zoom or Meet tab, upload audio, or paste a transcript. No bots join your calls.
🔎 Everything lives in your browser's local database, searchable, exportable as Markdown.

It is free and open source. Clone it and run your first meeting in under a minute:

https://sard.alaasi.dev
https://github.com/AbdulrahmanAlaasi/sard

Built with TypeScript + Vite, Whisper via transformers.js, and a runtime-agnostic local LLM layer. 113 automated tests.

If you care about meetings that stay private, I would love your feedback.

#buildinpublic #ai #privacy #meetings #opensource #localfirst

---

## LinkedIn post (Arabic, follow-up a few days later)

---

سرد: ملاحظات اجتماعات بالذكاء الاصطناعي، من غير ما يطلع الصوت من جهازك.

التفريغ يعمل داخل المتصفح، والنموذج اللغوي يعمل على جهازك، والملاحظات مرتبة: ملخص، نقاط أساسية، قرارات، ومهام. مجاني ومفتوح المصدر.

https://sard.alaasi.dev

---

## Carousel: 6 images (1200×750, generated from marketing/carousel/*.html)

Ready-made slides live in `marketing/carousel/` as self-contained HTML files in the
Sard brand; open one in a browser at 1200×750 and screenshot it (or use the PNGs if
already exported alongside).

1. `slide1-hero.html` · "Meeting notes that narrate themselves." + سرد mark
2. `slide2-private.html` · "Your audio never leaves your machine." local pipeline
3. `slide3-receipts.html` · "Notes with receipts." action item + timestamp
4. `slide4-capture.html` · the four capture modes
5. `slide5-honest.html` · "Never invented." owners/dates only when said
6. `slide6-open.html` · "Free. Local. Open source." + GitHub URL

Post order on LinkedIn: 1, 2, 3, 5, 4, 6.

## Video: 45-second screen recording

| t | Shot | Caption |
|---|---|---|
| 0-5s | Landing hero scrolls | "Meetings deserve a narrator." |
| 5-12s | Click Record microphone, speak two sentences about a project deadline | "Transcribed in your browser. Audio never leaves." |
| 12-20s | Transcript appears with timestamps, click Generate notes | "Your local AI writes the story." |
| 20-30s | Notes appear; hover an action item and a decision | "Owners and dates only when they were said." |
| 30-38s | Search the meeting library, export Markdown | "Searchable. Exportable. Yours." |
| 38-45s | End card: logo + سرد + sard.alaasi.dev | "Free. Local. Open source." |

Record at 1080p, light OS theme, cursor smoothing on. Export 4:5 for LinkedIn and
16:9 for the README.

## Distribution checklist

- LinkedIn EN post + carousel + video; reply to every comment for the first 2 hours.
- r/selfhosted + r/LocalLLaMA: lead with "no cloud, no bots" and the local LLM layer.
- Arabic dev Twitter/X thread with the Arabic post.
- Personal site alaasi.dev: writeup "A meeting notetaker with no server".
