# AeroKids production map

This file is the source of truth for production naming and URLs.

## Brand

Canonical brand spelling: **AeroKids**.

## Public website

- Canonical URL: https://aerokids.space
- Repository branch: `main`
- Hosting: GitHub Pages
- Technical fallback: https://korchakv.github.io/aerokids/
- `www.aerokids.space` is an alias only; public links should use `aerokids.space`.

## CRM

- Canonical staff URL: https://crm.aerokids.space
- Repository branch: `crm-v1`
- Render service: `aerokids-crm`
- Technical fallback: https://aerokids-crm.onrender.com
- Do not use the Render fallback in normal staff instructions.

## API

- Render service: `aerokids-crm-api`
- URL: https://aerokids-crm-api.onrender.com
- Infrastructure/API only; not a user-facing website.

## Database

- Provider: Neon
- Project: `aerokids-crm-production`
- Production organization slug: `aerokids`

## Branch policy

- `main` = website production only.
- `crm-v1` = CRM production only.
- `crm-*`, `website-*`, and `codex/*` are temporary work branches, not production variants.
- `old-site`, `aerokids-v2`, and `backup-*` are archival references only.
- New work starts from the appropriate production branch and returns through a pull request.
