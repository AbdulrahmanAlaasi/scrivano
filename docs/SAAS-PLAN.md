# Sard · SaaS Readiness Plan

Status today: local-first SPA live at sard.alaasi.dev (free, complete), open-source
backend (Django + Supabase, 58 tests) that anyone can self-host. What follows is the
gap list to a paid, managed product, in priority order.

## P0 · Ship the managed backend (1 to 2 weeks)

1. **Host the Django API.** Cloudflare Pages cannot run Django; use Fly.io or Railway
   (Dockerfile + gunicorn + WhiteNoise), pointed at the existing Supabase Postgres.
   Domain `api.sard.alaasi.dev`. Add `django-cors-headers` allowing only the app origin.
2. **Supabase RLS policies** on every workspace table (defense-in-depth behind the
   scoped managers) and rotate the credentials that passed through chat.
3. **Ops basics:** Sentry (backend + frontend), UptimeRobot on a health endpoint,
   daily Postgres backups (Supabase PITR), structured logging.
4. **Preconfigured cloud:** ship the app with the managed server URL + anon key baked
   in as defaults so "Cloud workspace" is one click, not a config form.

## P1 · Monetization plumbing (week 3)

- **Billing:** Lemon Squeezy (merchant of record, handles VAT, works for solo devs)
  with a `subscriptions` table keyed by workspace; webhook → plan flag; enforce limits
  in DRF permissions (free: 1 group, 10 cloud meetings; paid: unlimited).
- **Plans:** Local $0 forever · Team Cloud $8/member/month (founding: $5 lifetime
  lock-in for first 50 workspaces) · Self-hosted free.
- **Founding-access funnel now, billing later:** the landing page already collects
  interest via email; convert manually until volume justifies automation.

## P2 · Product completeness (weeks 4 to 6)

- Client-side extraction pipeline: after local notes generation, offer "Publish cited
  intelligence" mapping notes to the intelligence API with segment citations.
- Group document upload UI (backend already supports it), people directory UI,
  transcript editing, meeting templates.
- pgvector + FTS retrieval upgrade behind the existing retrieval interfaces.
- Email invitations (Supabase magic links) and notification digests.
- Desktop companion (Tauri) for system audio: the Phase 2 wedge feature.

## P3 · Trust for teams

SOC2-lite security page, DPA template, data-retention setting per workspace, audit
log UI (model exists), export-everything endpoint, account deletion.

## How Abdulrahman benefits

1. **Direct revenue:** founding lifetime deals ($5/member/month) target: 10 workspaces
   × 5 members ≈ $250 MRR as proof, then $8 standard.
2. **Data-residency consulting:** the self-host story sells services to Gulf/MENA
   companies that cannot ship audio to US clouds; Sard is the demo and the deliverable.
   One deployment engagement is worth more than months of early MRR.
3. **Portfolio compounding:** Sard is the flagship of alaasi.dev; every feature ships
   with a public writeup (isolation testing, citation validation) that doubles as
   hiring-grade evidence and SEO.
4. **Open-core leverage:** the backend stays open source (adoption, trust, issues),
   the managed hosting and future desktop app are the paid convenience.

## Launch checklist

- [ ] api.sard.alaasi.dev live + CORS + Sentry
- [ ] RLS + credential rotation
- [x] Founding-access email capture wired (mailto on landing)
- [ ] Product Hunt draft, r/selfhosted post, Arabic dev-Twitter thread
- [ ] LinkedIn post + 6 screenshots + 45s video (docs/MARKETING.md)
