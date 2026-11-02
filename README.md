# nadoo-ops
Scheduled, LLM-free ops checks (GitHub Actions). Problems are reported as issues (labels `health`, `seo`); issues close automatically when resolved.
- `health.yml` — weekdays 08:45 KST: failed Actions runs (last 26h) across owner repos; Vercel team production deployment state. Secret: `VERCEL_TOKEN`.
- `seo.yml` — monthly 1st 10:10 KST: title, meta description, og:title, og:image, canonical, html lang, robots.txt, sitemap.xml, JSON-LD, noindex for `sites.json`. Results in `data/`; an issue opens only if a check got worse than last month.
