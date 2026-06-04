<!--
SPDX-FileCopyrightText: 2026 Arthur Mouraud
SPDX-License-Identifier: Apache-2.0
-->

# ADR-003 — Orchestrator Frontend Strategy

- **Status**: Accepted
- **Date**: 2026-06-03 (Accepted 2026-06-04)
- **Deciders**: Arthur Mouraud
- **Scope**: orchestrator/ (frontend stack, SSE auth transport, build pipeline, bundling shape)
- **Context tags**: orchestrator, frontend, sse, auth

## Context

ADR-002 (Accepté 2026-06-03) verrouille le mode de démarrage : `python -m orchestrator.launcher` invoque `docker compose up -d`, attend le healthcheck, ouvre le navigateur sur `http://127.0.0.1:8000`. La stack Docker (FastAPI + RQ + Redis + MLflow) est désormais **invariante**. Le frontend doit s'inscrire dans cette enveloppe : il sera soit servi statiquement par FastAPI (`StaticFiles`), soit en process séparé pendant le dev.

L'API exposée par WP-3 est stable : **18 routes REST + 2 streams SSE** (`/api/v1/runs/{id}/logs`, `/api/v1/runs/{id}/metrics`), schéma OpenAPI complet sur `/api/openapi.json`. Le périmètre MVP frontend est petit (4 écrans : liste runs, détail run, submit, artifacts) et entièrement décrit par l'OpenAPI — la génération de client TypeScript est triviale.

Trois contraintes structurelles dictent le choix :

1. **EventSource ne supporte pas les headers custom** — décision verrouillée d'`arch_orchestrator.md` : auth Bearer statique sur tous les endpoints, y compris SSE. L'API navigateur native `new EventSource(url)` ne peut pas attacher `Authorization: Bearer …`. Trois workarounds existent : (a) token en query-string `?token=…`, (b) cookie `HttpOnly` posé par une route `/login`, (c) polyfill `@microsoft/fetch-event-source` (~6 KB) qui passe par `fetch()` et supporte les headers.
2. **ORC-004 de `SECURITY_AUDIT_2026-06-03.md`** défère explicitement le choix de transport SSE-auth à cet ADR, en notant que (a) est un anti-pattern (logs uvicorn, history navigateur, `document.referrer`).
3. **Profil Arthur** (`memory/user_profile.md`) : Python-strong, frontend-learning, Windows dev, préfère la simplicité à la sophistication, solo dev, scope single-user / single-machine (`CLAUDE.md`).

Quatre stacks ont été identifiées : **A** SvelteKit + codegen OpenAPI + polyfill SSE ; **B** Vite + React + TanStack Query + `openapi-fetch` + Tailwind ; **C** HTMX rendu par FastAPI (Jinja2) + `htmx-sse` ; **D** Streamlit/Gradio en conteneur séparé.

## Decision

**Option retenue : B — Vite + React + TypeScript + TanStack Query + `openapi-fetch` + Tailwind (DaisyUI) + `@microsoft/fetch-event-source`.**

Auth-with-SSE : **polyfill `@microsoft/fetch-event-source`** (~6 KB, supporte les headers), pas de cookie de session, pas de token en query-string. Le frontend stocke le Bearer en mémoire (récupéré au boot via prompt si non fourni, ou via variable Vite `VITE_API_TOKEN` en dev) et le passe en header sur tous les appels — REST et SSE — de façon uniforme.

Concrètement, à créer :

- `frontend/` à la racine du repo orchestrator (pas de monorepo séparé, pas de second conteneur).
- `frontend/package.json` : `vite`, `react`, `react-dom`, `@tanstack/react-query`, `react-router-dom`, `openapi-fetch`, `@hey-api/openapi-ts` (devDep, codegen), `@microsoft/fetch-event-source`, `tailwindcss`, `daisyui`, `typescript`.
- `frontend/src/api/generated/` : sortie de `openapi-ts` à partir de `http://127.0.0.1:8000/api/openapi.json`, regénérée par `npm run codegen`.
- Build pipeline : `npm run build` produit `frontend/dist/`. Le conteneur `api` mount (ou COPY au build de l'image) ce répertoire et FastAPI le sert via `app.mount("/", StaticFiles(directory="frontend/dist", html=True))` après tous les routers `/api/*`.
- Dev workflow : `vite dev` sur port 5173 avec proxy vers `127.0.0.1:8000/api`, hot-reload, codegen en watch.
- Makefile : `make frontend-install`, `make frontend-dev`, `make frontend-build`. `make start` (ADR-002) gagne une dépendance optionnelle sur `frontend/dist` si présent.

Conséquence : le launcher ADR-002 ouvre désormais `http://127.0.0.1:8000/` (frontend) au lieu de `/api/docs`. `/api/docs` reste accessible pour les power-users.

## Rationale

Comparaison des 4 stacks selon les critères pondérés (1-5, poids Haut×3 / Moyen×2 / Bas×1) :

| Critère (poids) | A: SvelteKit | B: Vite+React | C: HTMX | D: Streamlit |
|---|---|---|---|---|
| Coût apprentissage frontend (Haut) | 3/5 (Svelte moins connu) | 4/5 (React = lingua franca, tutoriels infinis) | 5/5 (Python pur, ~10 attributs HTMX) | 5/5 (Python pur) |
| Compatibilité SSE + Bearer (Haut) | 4/5 (polyfill OK) | 4/5 (polyfill OK) | 3/5 (`htmx-sse` ne supporte pas headers nativement, query-string par défaut) | **2/5** (Streamlit SSE limité, pas de Bearer custom propre) |
| Réversibilité si scope change (Moyen) | 4/5 | 5/5 (extraction composants triviale) | 2/5 (tout couplé à FastAPI Jinja, fork nécessaire pour SPA) | 1/5 (Streamlit = aller simple) |
| Marge évolution frontend public (Moyen) | 4/5 | 5/5 (Next.js migration path) | 2/5 (HTMX scale mal pour state-heavy) | 1/5 |
| Densité écosystème / tutoriels (Moyen) | 3/5 | 5/5 (la plus grande communauté frontend) | 3/5 (niche grandissante) | 3/5 (ML-only) |
| Surface deploy/build (Bas) | 4/5 | 4/5 (Vite build → dist statique) | 5/5 (rien à builder) | 3/5 (conteneur séparé requis) |
| **Score pondéré** | **45** | **52** | **42** | **30** |

Lecture :

- **D (Streamlit/Gradio) est éliminé structurellement.** Streamlit est conçu autour de son propre cycle `st.rerun()` + websocket interne ; consommer 2 streams SSE Bearer-authentifiés en parallèle (logs + metrics live) est un combat contre l'outil. Gradio même problème + UI moins flexible pour 4 écrans hétérogènes (table + détail + forms + artifacts). Le score "Python pur" séduit Arthur, mais il s'effondre dès qu'on regarde le fit SSE et la réversibilité.
- **C (HTMX) est tentant pour un profil Python-strong.** Pas de toolchain JS, rendu serveur, simplicité brute. Mais trois frictions : (1) `htmx-sse` ne supporte pas les headers Authorization, le pattern documenté est `?token=…`, ce qui re-tombe directement dans l'anti-pattern ORC-004 ; (2) le codegen OpenAPI/TypeScript devient inutile alors que l'API est déjà décrite en OpenAPI — on perd un actif gratuit ; (3) la roadmap (`docs/ROADMAP.md` inference live, dataset browser MP4) est state-heavy : HTMX peut le faire, mais avec frictions croissantes (`hx-trigger` + Alpine.js pour le state local). Pour un MVP **statique** (4 listes + 1 form), HTMX serait gagnant. Pour un MVP **avec 2 SSE temps réel et un graphe métriques live**, le rapport effort/bénéfice s'inverse.
- **A (SvelteKit) est le challenger sérieux.** Moins de boilerplate que React, reactivity built-in, `+page.server.ts` matche bien le pattern "lire OpenAPI au build". Mais : (a) écosystème plus petit, moins de tutoriels quand Arthur va bloquer sur un détail (et il va bloquer, c'est du frontend-learning) ; (b) DaisyUI/shadcn-équivalents Svelte existent mais sont moins matures ; (c) SvelteKit pousse vers du SSR/edge alors qu'on veut du SPA statique servi par FastAPI — on n'utiliserait que 30% de SvelteKit, c'est un signe que l'outil dépasse le besoin.
- **B (Vite + React) gagne par robustesse écosystémique.** React est la lingua franca frontend : quand Arthur cherche "react sse authentication tanstack query", il trouve 50 tutoriels ; quand il cherche "sveltekit fetch-event-source", il en trouve 3 dont 2 obsolètes. Pour un frontend-learner solo, la densité de docs vaut plus que l'élégance syntaxique. `openapi-fetch` + types générés rendent les appels REST type-safe sans la couche TanStack Router/RPC ; Tailwind + DaisyUI fournit les composants pré-stylés (table, modal, form, toast) sans concevoir un design system. Le bundle Vite build est statique pur — se sert par `StaticFiles`, pas de Node en prod, cohérent avec ADR-002.

Critère décisif : **densité documentaire pour un solo dev frontend-learning**. SvelteKit serait techniquement légèrement supérieur si Arthur était déjà à l'aise en frontend ; ici la marge d'erreur (chercher de l'aide, recopier un pattern, déboguer un edge case TanStack Query × EventSource) doit être maximale. React maximise cette marge.

## Consequences

### Positives

- Codegen TypeScript depuis `/api/openapi.json` → tous les calls REST sont type-safe, refactor côté API détecté à `npm run codegen` (= en CI, future job).
- TanStack Query gère cache, retries, invalidation, optimistic updates de façon idiomatique — le pattern "submit run → invalider la liste → afficher dans la table" est ~3 lignes.
- Tailwind + DaisyUI : 4 écrans bâclables en un sprint sans design system custom ; toggle dark mode gratuit si demandé un jour.
- Build statique pur, servi par `StaticFiles` dans le conteneur `api` existant — zéro nouveau service Docker, zéro changement à ADR-002. `make start` ouvre `/` qui sert le frontend, `/api/docs` reste pour les power-users.
- Polyfill `@microsoft/fetch-event-source` : un seul transport (header `Authorization: Bearer …`) pour REST **et** SSE, code uniforme, pas de branche d'auth spéciale par endpoint.
- Réversibilité : si dans 6 mois le scope grossit (multi-user, public-facing), migration vers Next.js est un chemin documenté ; si au contraire on dégonfle, retirer React et garder un index HTML statique est trivial.

### Négatives / trade-offs acceptés

- Toolchain Node ajoutée au repo (`package.json`, `node_modules`, `vite`). Arthur n'est pas frontend-natif → courbe d'apprentissage 1-2 semaines pour se sentir productif en React+TanStack Query. C'est le coût d'avoir un frontend.
- ~6 KB de polyfill `@microsoft/fetch-event-source` au lieu de l'API native EventSource. Trivial sur un frontend local.
- Bundle JS livré au client (vs HTMX où tout est HTML serveur). Pour 4 écrans en single-user, le coût est invisible. Pour un futur déploiement public, il faudra revoir.
- Le codegen OpenAPI doit être ré-exécuté quand l'API change. Mitigation : job CI optionnel + diff-check, ou simplement `npm run codegen` documenté dans `RUNBOOK.md`.

### Hors-scope explicite

- **Multi-user auth / SSO / RBAC** — single-user verrouillé par `arch_orchestrator.md`.
- **Dataset preview MP4** — différé (`docs/ARCHITECTURE.md` v0.1 non-goals).
- **Inference live UI** — différé tant que `POST /api/v1/infer` n'existe pas.
- **Design system custom** — DaisyUI suffit.
- **i18n** — single-user, EN/FR mélangés acceptés en interne.
- **Dark mode toggle, animations, transitions soignées** — gratuit via DaisyUI plus tard, hors MVP.
- **Tests E2E frontend (Playwright)** — out-of-scope MVP, à ajouter quand le frontend stabilise.
- **PWA / offline / installable** — pas de besoin single-machine.

## Auth-with-SSE choice

**Workaround retenu : polyfill `@microsoft/fetch-event-source`.**

Analyse des trois options face à ORC-004 :

1. **Token en query-string `?token=…`** — rejeté. L'audit explicite que la valeur fuit dans (a) les access logs uvicorn, (b) l'historique navigateur, (c) `document.referrer` vers tout asset externe, (d) toute capture d'écran de l'URL. Le sanitizer regex SSE de `streams.py` ne couvre pas le token dans l'URL. **Anti-pattern.**
2. **Cookie HttpOnly posé par `/login`** — viable mais coûteux : il faut ajouter une route `/login` + `/logout`, gérer CSRF (mitigé par bind 127.0.0.1 mais à documenter), gérer l'expiration, et migrer les 16 routes non-SSE à accepter aussi le cookie. Cela double la surface d'auth pour économiser 6 KB de polyfill. ROI négatif.
3. **Polyfill `@microsoft/fetch-event-source`** — **retenu**. Bibliothèque mature (Microsoft, 1M+ DL/semaine), ~6 KB gzip, API compatible EventSource, supporte `headers`, `signal` (cancellation propre), retry custom. Permet de garder **un seul modèle d'auth** sur les 18 routes REST et les 2 streams SSE : `Authorization: Bearer …` en header, partout. Le code orchestrator côté serveur (`streams.py`, `auth.py`) n'a **rien** à changer — c'est précisément la propriété qu'on cherche.

Conséquence sécurité positive : le token n'apparaît **jamais** dans les logs uvicorn (header non-loggé par défaut), jamais dans l'history navigateur, jamais dans `document.referrer`. Stocké en mémoire JS (pas localStorage, pour limiter le surface XSS — bien que XSS en single-user soit un risque marginal, la discipline est gratuite). Au boot, le frontend lit `import.meta.env.VITE_API_TOKEN` en dev (injecté par Vite depuis `.env.local`) ou prompt l'utilisateur en prod (`prompt()` ou modal au premier appel 401).

Note : cette décision **ne ferme pas** la porte à un cookie de session plus tard si le scope passe multi-user — la couche `openapi-fetch` est trivialement remplaçable.

## Implementation outline

Étapes pour un follow-up plan (pas une implémentation ici) :

1. Créer l'arborescence `frontend/` à la racine du repo, avec `package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js`, `postcss.config.js`. Ajouter `frontend/node_modules/` et `frontend/dist/` au `.gitignore`.
2. Installer les deps : `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `openapi-fetch`, `@microsoft/fetch-event-source`, `tailwindcss`, `daisyui` ; devDeps `vite`, `@vitejs/plugin-react`, `typescript`, `@hey-api/openapi-ts`, `@types/react`, `@types/react-dom`.
3. Configurer `vite.config.ts` avec `server.proxy: { '/api': 'http://127.0.0.1:8000' }` pour le dev, et `build.outDir: 'dist'` pour la prod.
4. Ajouter `npm run codegen` : script `openapi-ts` lisant `http://127.0.0.1:8000/api/openapi.json` (en dev) ou un snapshot committé `frontend/openapi.snapshot.json` (en CI), sortie dans `frontend/src/api/generated/`.
5. Créer `frontend/src/api/client.ts` : un wrapper `openapi-fetch` partagé qui injecte le header `Authorization` depuis un store (Zustand minimal ou Context React), et un wrapper SSE `createAuthedSSE(url, onMessage)` basé sur `@microsoft/fetch-event-source` qui injecte le même header.
6. Implémenter la couche routing (`react-router-dom`) avec 4 routes : `/runs`, `/runs/:id`, `/submit`, `/artifacts`. Layout commun avec sidebar DaisyUI.
7. Implémenter l'écran **Runs list** : `useQuery(['runs'])` → `GET /api/v1/runs`, table DaisyUI avec filtres par `status` et `job_type`, refetch toutes les 5s tant qu'il y a un run `running`/`queued`.
8. Implémenter l'écran **Run detail** : metadata via `GET /api/v1/runs/:id`, deux panneaux live alimentés par `createAuthedSSE` (logs : append-only terminal-like, virtualisé ; metrics : graphe ligne `recharts` ou `visx`).
9. Implémenter l'écran **Submit** : 3 forms (`react-hook-form`) avec dropdowns peuplés par `GET /api/v1/configs/{envs,policies,…}`, validation côté client miroir des Pydantic schemas, `hydra_overrides` saisi comme `key=value` (multi-line), `POST /api/v1/runs/{collect,train,eval}` au submit, redirect vers le détail du run créé.
10. Implémenter l'écran **Artifacts** : 3 listes (checkpoints, eval_reports, datasets) via `GET /api/v1/artifacts/*`, liens download avec header Bearer (le client `openapi-fetch` retourne le blob, on déclenche le download via `URL.createObjectURL`).
11. Configurer le bundling final : `make frontend-build` produit `frontend/dist/`, le `Dockerfile` de l'image `api` ajoute un stage `COPY frontend/dist /app/static`, et `src/orchestrator/api/main.py` mount `app.mount("/", StaticFiles(directory="/app/static", html=True))` après tous les `app.include_router` (pour ne pas écraser `/api/*`).
12. Mettre à jour ADR-002 launcher : `webbrowser.open` cible désormais `http://127.0.0.1:8000/` (frontend). `/api/docs` reste accessible mais n'est plus la landing. Documenter dans `README.md` quickstart : `make install && make token && make frontend-install && make frontend-build && make start`.

## Alternatives considered (et rejetées)

- **A — SvelteKit + `@hey-api/openapi-ts` + `@microsoft/fetch-event-source`.** Techniquement séduisante (moins de boilerplate, reactivity built-in), mais densité documentaire inférieure pour un solo dev frontend-learning. Le delta DX vs React est réel mais ne compense pas le coût "j'ai un bug obscur et personne sur Stack Overflow ne l'a eu". À reconsidérer si Arthur monte en compétence frontend ou si une équipe le rejoint.
- **C — HTMX + Jinja2 + `htmx-sse`.** Très attirant côté "Python pur, zéro toolchain JS". Rejeté pour trois raisons cumulatives : (1) `htmx-sse` documente `?token=…`, donc impose l'anti-pattern ORC-004 ou un détour cookie qui défait sa simplicité, (2) on perd la valeur du codegen OpenAPI déjà payée par WP-3, (3) la roadmap (inference live, dataset MP4 preview) est state-heavy et HTMX scale mal sur ce profil. Bon choix pour un MVP **sans SSE** ; mauvais choix ici précisément à cause des 2 streams temps réel.
- **D — Streamlit / Gradio en conteneur séparé.** Rejeté pour incompatibilité structurelle : SSE custom-headers Bearer-authentifiés ne s'inscrit pas dans le cycle de rerun Streamlit ; Gradio même problème. De plus, conteneur séparé = nouvelle surface Docker contre l'invariant ADR-002 ("Docker stack inchangée"). Et la réversibilité est nulle : un dashboard Streamlit ne se ré-architecte pas, il se réécrit.

## Invariants préservés

Décisions verrouillées qui restent intactes après ce choix :

- Stack `FastAPI + SQLite + RQ + Redis` inchangée (ADR-002 + `arch_orchestrator.md`).
- Bind `127.0.0.1` + Bearer token statique inchangé — le frontend respecte le même contrat d'auth qu'un client `curl`.
- Streaming SSE inchangé côté serveur (`api/routes/streams.py` ne bouge pas).
- Scope ML batch only inchangé — pas d'endpoint frontend qui pousserait à ajouter `/infer`.
- Pattern subprocess Hydra inchangé.
- Règle "ne jamais modifier les 4 sibling repos" inchangée — `frontend/` vit dans le repo orchestrator uniquement.
- ADR-002 launcher inchangé dans sa nature (juste l'URL d'ouverture qui passe de `/api/docs` à `/`).
- 18 routes + 2 SSE — pas d'endpoint ajouté pour le frontend (pas de `/login`, pas de session cookie).

## References

- `docs/adr/ADR-002-wrapping-strategy.md` (launcher Python, stack Docker invariante)
- `docs/SECURITY_AUDIT_2026-06-03.md` (ORC-004 défère le choix SSE-auth à cet ADR)
- `docs/ARCHITECTURE.md` (18 routes, 2 streams SSE, modèle d'auth Bearer)
- `memory/arch_orchestrator.md` (4 décisions verrouillées : bind 127.0.0.1, Bearer, SSE, ML batch)
- `memory/user_profile.md` (profil Arthur : Python-strong, frontend-learning, Windows dev, solo)
- `CLAUDE.md` (single-user, single-machine, repo conventions)
- `@microsoft/fetch-event-source` (https://github.com/Azure/fetch-event-source) — polyfill SSE avec headers
- `@hey-api/openapi-ts` — codegen TypeScript depuis OpenAPI
