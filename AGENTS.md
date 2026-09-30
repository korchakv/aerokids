# AeroKiDS website: project brief for the coding agent

You are building a one-page marketing website for **AeroKiDS**, a small offline technology school in **Ivano-Frankivsk, Ukraine**. Read this whole file before writing code. A working visual prototype is provided as `reference/aerokids-prototype.html`. Treat it as the source of truth for look, structure and motion; rebuild it cleanly and extend it as described here.

All user-facing text is **Ukrainian**. Code, comments, file names and commit messages are **English**.

---

## 1. Business context

- **What it is:** an offline school (physical location in Ivano-Frankivsk). Tagline: "Школа сучасних технологій".
- **What is taught:** FPV drone piloting (simulator first, then real flights), building/assembling drones, electronics (Arduino, ESP32, sensors), programming, 3D modelling, and practical/technical use of AI as a helper tool. Robotics is planned for later; show it only as "Скоро" if at all.
- **Audiences:**
  - Children **10–16 years old**: ongoing club (гурток) format. Main audience. Decision-makers are **parents**, who care about safety, clear results and trust.
  - **Adults**: separate courses with a defined start/finish. Only a short block on the site for now.
- **Sales flow:** many kids try a **trial lesson** and decide later. The single goal of the site is to get a person to **message the school on Instagram Direct** to book a trial lesson.
- **Differentiator vs. other Ukrainian FPV schools** (most are military-operator training): this is a **civilian engineering school for kids**, where the drone is the entry point into electronics, code and AI. Tone: energetic, friendly, but serious about safety. Never militaristic.

## 2. Goals and non-goals

**Goals**
1. Explain in 10 seconds what the school is, for whom, and where.
2. Show the learning path (simulator, flights, building, Arduino/ESP32, code + AI, own project).
3. Reassure parents (safety, trial lesson, small steps).
4. Drive clicks to Instagram Direct (and optionally a phone call).
5. Feel premium and alive: scroll-driven and hover interactions, not a flat page.
6. Load fast on mobile 4G in Ukraine.

**Non-goals (do not build now)**
- No online payments, no user accounts, no blog, no CMS, no multi-language.
- No CRM. A separate internal Windows CRM is a different project. Do not touch it.
- Do not invent prices, schedules, phone numbers, addresses, reviews, teacher names, group sizes, statistics or certificates. Use clearly marked placeholders (see section 12).

## 3. Tech stack and project structure

Keep it simple and dependency-free at runtime.

- **Plain HTML + CSS + vanilla JS** (ES modules). No framework. Optional: Vite only as a dev server/bundler if you want image optimization, but the output must be a static folder.
- Deployable to **GitHub Pages / Netlify / Cloudflare Pages** with zero server code.
- No jQuery, no heavy animation libraries. Motion via CSS, `IntersectionObserver`, `requestAnimationFrame`. (GSAP/ScrollTrigger allowed only if it clearly saves code and is self-hosted; default is vanilla.)

```
/
├─ index.html
├─ AGENTS.md
├─ reference/aerokids-prototype.html   # visual/motion reference, do not ship
├─ assets/
│  ├─ img/            # WebP (+ JPG fallback) files, see section 9
│  ├─ logo/           # aerokids-logo.svg, aerokids-mark.svg, favicon files
│  └─ fonts/          # only if self-hosting fonts
├─ css/styles.css
├─ js/main.js
├─ robots.txt
├─ sitemap.xml
└─ README.md          # how to edit text, swap images, deploy
```

## 4. Brand and design system

The brand comes from the school's Instagram posters: **dark navy background, bright cyan accent, bold rounded headlines with a cyan "brush-stroke" highlight, thin cyan line icons, tech-lab photography with neon rim light.** Match that. The prototype is published at https://claude.ai/artifact/31eepKhVvjcJiDn4k2wQ3Z and is also supplied as a file; it already contains the real images and the real logo.

**Colour tokens (CSS custom properties on `:root`)**

| Token | Value | Use |
|---|---|---|
| `--bg` | `#050d1a` | page background |
| `--bg2` | `#0a1830` | alternate section background |
| `--card` | `#0c1d38` | cards |
| `--line` | `#17365c` | borders, grid, inactive timeline |
| `--tx` | `#f2f8fc` | main text |
| `--mut` | `#9db3c6` | secondary text |
| `--cy` | `#22e3f5` | primary accent, buttons, glow |
| `--ink` | `#04121f` | text on cyan |
| `--yl` | `#ffd93b` | secondary accent (electronics) |
| `--pu` | `#9b7bff` | secondary accent (building) |

- **Dark is the brand.** Also provide a light-scheme override for `prefers-color-scheme: light` and a `:root[data-theme="dark"]` override, as the prototype does. Body must always have an explicit background colour.
- **Typography (all Google Fonts with Cyrillic; prefer self-hosted WOFF2 subsets latin + cyrillic):** chosen from 2026 trends: a futuristic rounded display face for headings, a modern neo-grotesque for text, handwritten accents for warmth, and a mono face for tech tags.
  - **Display:** `Unbounded` 600/700/800 (variable). H1 is **UPPERCASE** 800 (like the Instagram posters); H2 is sentence case 700; H3 700; numbers 800. Use `text-wrap: balance` and `hyphens: auto` on headings because the face is wide.
  - **Body and UI:** `Onest` 400/500/700, 18px base, line-height 1.65, line length at most about 65 characters; buttons 700.
  - **Handwritten accents:** `Caveat` 700, about 32px (27px on mobile), cyan, rotated about -2.5deg, used as short notes above headings or under the hero buttons (copy: "Реальні навички. Яскраві емоції.", "Вчимося через практику", "Без зобов'язань", "Чекаємо в AeroKiDS!"). Max one note per section.
  - **Mono:** `JetBrains Mono` 700 only for the marquee strip of tech words.
  - Scale: H1 `clamp(30px,4.5vw,60px)`, H2 `clamp(24px,3.5vw,40px)`, H3 `clamp(17px,1.9vw,20px)`, lead paragraph 19px. `font-display: swap`, real fallback stacks, `font-synthesis: none`.
- **Brush highlight:** a cyan block behind key headline words, slightly rotated (about -1.6deg) with a rough `clip-path` polygon edge (see `.brush` in the prototype). Use it sparingly: hero headline and the final CTA headline only.
- **Logo:** the client's **original logo is final and must be used exactly as supplied** (`assets/logo/aerokids-logo-original.png`, a circular badge with the cyan drone-X mark and the school name on a near-black background). **Do not redraw, recolour, re-typeset or animate the logo.** Show it static in the header (about 48px) and in the footer. Generate favicon sizes from it (32, 180, 512 PNG).
- **Shape language:** large radii (16–22px) on cards and buttons, thin 1px borders, cyan glow for emphasis. Avoid generic stock-looking gradients.
- **Copy rules:** sentence case, active voice, short sentences, plain words. Uppercase only for H1, H2 and the marquee strip.

## 5. Page structure (single page, anchored sections)

Order and IDs:

1. **Header** (fixed, blurred): logo, nav anchors (`#napryamky`, `#shlyah`, `#probne`, `#faq`), button "Записатися" to `#contact`. On mobile hide links, keep logo + button.
2. **Hero** (`#top`): H1 "Не просто гурток: *навички для майбутнього*" (second part in brush highlight). Sub: "Керуємо дронами в симуляторі, збираємо їх власноруч, програмуємо Arduino та ESP32 і вчимося застосовувати AI. Івано-Франківськ, діти 10–16 років." Buttons: primary "Записатися на пробний урок" (to Instagram Direct), ghost "Що ми вивчаємо" (to `#napryamky`). Right side: `hero-photo` as a **circle** (inset about 7%, `background-size` about 120% positioned on the drone, 4px cyan ring and soft cyan glow) with two dashed circular outlines slowly rotating in opposite directions behind it. No text chips or labels on the photo. The logo itself is never animated.
3. **Marquee strip:** ARDUINO, ESP32, FPV-ДРОНИ, РОБОТИ, ПРОГРАМУВАННЯ, 3D-МОДЕЛЮВАННЯ, + AI. Infinite CSS scroll, `aria-hidden`.
4. **Facts row:** "4 напрямки", "10–16 років", "1 пробний урок" with short captions. Numbers count up when visible.
5. **Напрямки** (`#napryamky`): H2 "Що роблять діти в AeroKiDS". Four cards:
   - Керують (cyan): "FPV-пілотування спершу в симуляторі, безпечно й без поломок."
   - Збирають (purple): "Дрони та моделі: рама, мотори, паяння, налаштування."
   - Досліджують (yellow): "Arduino, ESP32, датчики: як електроніка відчуває світ."
   - Створюють (blue `#4da3ff`): "Код, 3D-моделі та робота з AI для власних проєктів."
   Each card: image slot (4:3), round icon badge in the card colour, title, one sentence. Line-icon style for the badges (replace the emoji in the prototype with inline SVG icons: gamepad, wrench, chip, cube/code).
6. **Шлях учня** (`#shlyah`): vertical timeline with six steps: Симулятор; Перші польоти; Збірка дрона; Arduino та ESP32; Код і AI; Власний проєкт (descriptions in the prototype). A cyan progress line fills as the user scrolls; steps light up in turn.
7. **Пробний урок** (`#probne`): three boxes: 1 "Напишіть у Direct", 2 "Прийдіть на урок", 3 "Вирішіть разом".
8. **Безпека:** H2 "Безпека на першому місці" with a checklist: захисні окуляри; спочатку симулятор, потім реальний дрон; чіткі правила поведінки; заняття під наглядом викладача.
9. **Для дорослих:** a short band (add this; it is not yet in the prototype): "Дорослим: окремі курси" with one sentence and a button to Direct. No details until the client supplies the programme.
10. **FAQ** (`#faq`): native `<details>` accordion, first item open, intro line with a link to Direct. Ten questions with full answers (exact copy is in the prototype; keep it, and also emit it as `FAQPage` JSON-LD):
    1. Для кого цей гурток?
    2. Чи потрібен досвід у техніці або програмуванні?
    3. Що саме вивчають діти?
    4. Чи безпечно вчитися керувати дроном?
    5. Навіщо дітям вивчати AI?
    6. Чи потрібно купувати дрон, ноутбук або набір?
    7. Як проходить пробний урок?
    8. А якщо дитині не сподобається?
    9. Чи є заняття для дорослих?
    10. Як записатися й де ви знаходитесь?
11. **Контакти / запис** (`#contact`): H2 "Запис на *пробний урок*", big button "Написати в Direct", contact line with address, phone, Instagram (placeholders), optional map embed slot.
12. **Footer:** "AeroKiDS · Школа сучасних технологій · Івано-Франківськ".

Optional later sections, leave hooks but do not build now: Викладачі, Галерея, Відгуки, Проєкти та змагання, Ціни.

## 6. Interactions and motion (must-haves)

Reproduce these from the prototype, then polish:

- **Scroll progress bar** at the top (scaleX by scroll).
- **Reveal on scroll:** `.rv` elements fade/slide in once via `IntersectionObserver`, with a small stagger.
- **Hero parallax:** the background grid and the hero stage move at different speeds on scroll.
- **Hero background zoom:** `hero-bg` slowly zooms in (scale 1 to about 1.22), drifts down and fades to about 50% while the user scrolls through the first screen. The dashed circles around the hero photo rotate slowly.
- **Timeline fill:** progress line height and step highlighting driven by scroll position.
- **Card tilt:** 3D tilt following the pointer on the four direction cards, and **cursor glow** following the mouse. **Only when `(hover:hover)` matches.**
- **Count-up** for the facts row.
- **Marquee** strip.
- **Buttons:** hover lift + cyan glow.

Recommended upgrades (implement if they stay light):
- A short intro on load (hero photo scales in, headline reveals), once, under 1.2s.
- Smooth image fade-in when lazy images load.
- Magnetic effect on the primary CTA (desktop only).

**Motion rules**
- Respect `prefers-reduced-motion: reduce`: disable animations, show all content immediately, hide the flying drone and glow.
- Use `transform` and `opacity` only for animated properties. Throttle scroll handlers with `requestAnimationFrame` and `{passive:true}`.
- No layout shift (CLS < 0.05): reserve space for all images with `aspect-ratio`.
- Keep the main thread quiet; total JS under ~15 KB gzipped.

## 7. Conversion and contacts

- Primary CTA everywhere = **Instagram Direct**. Direct URL: `https://ig.me/m/aerokids.if` (profile: `https://www.instagram.com/aerokids.if/`). Keep the handle `aerokids.if` in **one constant** (`const IG_HANDLE` in `js/main.js`) and build all Instagram links from it. Open them in a new tab with `rel="noopener"`.
- Secondary: `tel:` link and, if provided, Telegram/Viber links. Show them as buttons on mobile.
- **Optional phase 2 (do not build unless asked):** a lead form (name, phone, for child/for self, child age, comment). If built, it must POST to a **serverless function** (Cloudflare Worker / Netlify Function) that forwards to a Telegram bot. **Never put the bot token in client code.** Add a honeypot field and basic rate limiting. The form must degrade gracefully to the Direct button.

## 8. SEO, sharing, analytics

- `<html lang="uk">`, one `<h1>`, logical heading order.
- Title: "AeroKiDS — школа FPV-дронів, Arduino, ESP32 та AI в Івано-Франківську". Meta description about 150 characters, Ukrainian, mentions FPV, Arduino, ESP32, AI, children 10–16, Івано-Франківськ.
- Open Graph + Twitter card with `og-share` image (1200×630), canonical URL (placeholder domain), favicon set (SVG + PNG 32/180/512), `theme-color` `#050d1a`.
- **JSON-LD** `EducationalOrganization` / `LocalBusiness` with name, address locality (Івано-Франківськ), `sameAs` (Instagram), `areaServed`; fill unknown fields from the placeholder config only when real values exist.
- `robots.txt`, `sitemap.xml`.
- Analytics: default none. If added, use privacy-friendly **Plausible** or Cloudflare Web Analytics, and track clicks on the Direct button, the phone button and the adult-courses button as custom events.

## 9. Images and assets

**All images are already supplied** in `assets/img/` (optimized WebP plus JPG fallback, file names exactly as in the table below). The client generated them with an AI tool and will later overwrite them with real photos of the school. Keep a tasteful gradient fallback on every image slot so the page still looks finished if a file fails to load.

| File | Size | Used in | Notes |
|---|---|---|---|
| `hero-photo` | 1200×1200 | hero, circular crop (keep the drone near the centre) | a real-looking teen-club desk with a colourful FPV drone, headphones, gamepad, Arduino; no people |
| `hero-bg` | 2400×1350 | hero background layer | dark lab, empty space on the left |
| `card-simulator` | 800×600 | card "Керують" | teen with headphones at simulator |
| `card-build` | 800×600 | card "Збирають" | hands soldering flight controller |
| `card-electronics` | 800×600 | card "Досліджують" | Arduino UNO, ESP32, breadboard on blueprint grid |
| `card-code` | 800×600 | card "Створюють" | laptop with code and 3D drone frame |
| `og-share` | 1200×630 | social preview | dark banner, empty left side |

- Deliver each as **WebP (quality ~80) plus a JPG fallback**, via `<picture>`. Add `width`/`height`, `loading="lazy"` (not for hero), `decoding="async"`, meaningful Ukrainian `alt` text (or empty alt for purely decorative).
- Hero image is the LCP element: `fetchpriority="high"`, preload it.
- Do not hotlink external images. No stock photos.
- Do not generate or fetch images yourself. `og-share-1200x630.jpg` is supplied for social previews (it needs an absolute URL once the domain is known).

## 10. Accessibility and quality bar

- WCAG AA contrast (check cyan-on-navy and ink-on-cyan; the light-scheme cyan is darker for this reason).
- Visible focus outlines on all interactive elements (yellow outline in the prototype).
- Full keyboard navigation; skip-to-content link; nav landmarks; `aria-hidden` on decorative animation.
- Touch targets at least 44×44px. Body text at least 16px. Line length under about 75 characters.
- Mobile first: test at 360, 390, 768, 1024, 1440px. No horizontal scroll. Respect iOS safe areas (`viewport-fit=cover`, `env(safe-area-inset-*)`) for the fixed header.
- Lighthouse targets (mobile): Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, SEO ≥ 95.
- Cross-browser: latest Chrome, Safari (iOS 16+), Firefox, Samsung Internet. Provide fallbacks where `color-mix`, `backdrop-filter` or `clip-path` are unsupported.

## 11. Content editing model

Make text easy for a non-developer to change: keep all copy in `index.html` (no templating), group "things to edit" at the top of `README.md` (Instagram handle, phone, address, domain), and use semantic class names. Document in `README.md` how to swap images and redeploy.

## 12. Placeholders and open questions (leave as TODO, do not invent)

- Phone number, street address, working hours, map location
- Domain name
- Prices, schedule, group sizes (not shown until provided)
- Teacher names/photos, reviews, gallery, competitions
- Adult course programme and pricing
- Whether Telegram/Viber links are wanted

Render placeholders visibly as "додати" in the UI so they are not missed, and list them in `README.md`.

## 13. Workflow and acceptance criteria

**Suggested order**
1. Scaffold the structure; port tokens, fonts, and layout from the prototype.
2. Build static sections with real copy; make it responsive.
3. Add interactions one by one; verify reduced-motion and touch behaviour.
4. Wire image slots and `<picture>` markup.
5. Add SEO, JSON-LD, OG, favicons.
6. Accessibility + Lighthouse pass; fix.
7. Write `README.md`; prepare deploy config (Netlify `netlify.toml` or GitHub Pages workflow).

**Done when**
- The page matches the prototype's look and motion on desktop and mobile.
- Every CTA points to the single Direct URL (or safely scrolls to `#contact` while the handle is a placeholder).
- Works with no images present and with images present.
- Reduced-motion and keyboard use are fully supported.
- Lighthouse targets in section 10 are met.
- No console errors, no external requests beyond fonts (if not self-hosted) and optional analytics.
- `README.md` explains editing and deployment to a non-developer.

**Working style**
- Make small, reviewable commits with clear English messages.
- If something in this brief is ambiguous or missing, **choose the simplest option, leave a `TODO:` comment, and list it in the final report** instead of inventing business facts.
- At the end, output a short report: what was built, what remains as placeholders, how to run and deploy.
