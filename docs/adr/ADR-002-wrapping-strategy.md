<!--
SPDX-FileCopyrightText: 2026 Arthur Mouraud
SPDX-License-Identifier: Apache-2.0
-->

# ADR-002 — Orchestrator Wrapping Strategy

- **Status**: Accepted 2026-06-03
- **Date**: 2026-06-03
- **Deciders**: Arthur Mouraud
- **Scope**: orchestrator/ (launch UX, deployment shape, frontend prep)
- **Context tags**: orchestrator, frontend-prep, deployment

## Context

L'orchestrator est en place en tant que stack `docker compose` multi-service (api FastAPI + worker RQ + redis + mlflow, voir `docker/docker-compose.yml`). L'UX actuelle se résume à `make up` puis ouverture manuelle de `http://127.0.0.1:8000/api/docs` — fonctionnel pour développer l'API, mais sans "lancement applicatif" lisible pour le futur frontend.

Le prochain sprint cible un frontend léger. Avant d'écrire le moindre client, il faut trancher **comment l'orchestrator se démarre et s'expose**, parce que ce choix conditionne :
- la façon dont le frontend pointe vers l'API (URL, port, lifecycle),
- la dépendance ou non à Docker côté utilisateur final,
- le packaging futur (binaire, app native, ou stack dev).

Les 4 décisions verrouillées dans `memory/arch_orchestrator.md` doivent rester intactes : bind `127.0.0.1` + Bearer token, SSE pour streaming, stack FastAPI/SQLite/RQ/Redis, scope ML batch. Le profil utilisateur (`memory/user_profile.md`) signale Arthur comme **Python-strong, frontend-learning**, dev Windows local + cible Linux/Kaggle GPU. Toute solution qui introduit une nouvelle toolchain (Rust, packaging natif complexe) coûte un temps d'apprentissage qui n'est pas dans le budget de la phase frontend.

Quatre options ont été identifiées : (A) status quo docker-compose, (B) launcher Python local qui wrappe compose, (C) app desktop Tauri avec sidecar, (D) PyInstaller + tray app avec uvicorn in-process.

## Decision

**Option retenue : B — Lanceur Python local (`python -m orchestrator.launcher`).**

Concrètement :
- Nouveau module `orchestrator.launcher` (single-file, ~150 LOC) exposé via `python -m orchestrator.launcher` et un alias Makefile `make start`.
- Le launcher exécute `docker compose -f docker/docker-compose.yml up -d`, poll le healthcheck HTTP `GET /api/v1/health` (qui existe déjà dans `docker-compose.yml`) avec backoff jusqu'à `start_period`, puis appelle `webbrowser.open("http://127.0.0.1:8000/api/docs")` (ou la racine frontend quand elle existera).
- Affiche en console un résumé clair : URL API, URL MLflow, où trouver le token (`.env`), commande pour arrêter (`make stop` / `python -m orchestrator.launcher --down`).
- La stack Docker reste **inchangée**. Le launcher est une enveloppe ergonomique au-dessus de `docker compose`, pas une réécriture.

Conséquence pratique : `make up` continue d'exister pour les utilisateurs avancés ; `make start` (ou `python -m orchestrator.launcher`) devient le point d'entrée recommandé, et c'est cette commande que la doc README pointera en premier.

## Rationale

Comparaison des options selon les critères pondérés du contexte :

| Critère (poids) | A: status quo | B: launcher Py | C: Tauri | D: PyInstaller+tray |
|---|---|---|---|---|
| Coût apprentissage Arthur (Haut) | 5/5 (rien) | 5/5 (Python natif) | 1/5 (Rust + Tauri) | 3/5 (pyinstaller + pystray) |
| Préserve 4 décisions verrouillées (Haut) | 5/5 | 5/5 | 4/5 | **2/5** (cf. ci-dessous) |
| Préserve la stack Docker actuelle (Haut) | 5/5 | 5/5 | 3/5 | **1/5** (la contourne) |
| Simplicité packaging/distribution (Moyen) | 2/5 (Docker requis) | 3/5 (Docker requis) | 5/5 (.msi/.dmg/.AppImage) | 4/5 (single binary) |
| Cross-platform Win/Linux/Mac (Moyen) | 4/5 | 4/5 | 5/5 | 4/5 |
| Marge d'évolution frontend / inference live (Moyen) | 4/5 | 4/5 | 5/5 | 3/5 |
| **Score pondéré (Haut×3, Moyen×2)** | **44** | **47** | **43** | **30** |

Lecture du tableau :

- **Option D est éliminée structurellement.** La décision verrouillée n°2 d'`arch_orchestrator.md` exige `FastAPI + SQLite + RQ + Redis`. RQ nécessite un Redis **réel** (pas `fakeredis`, qui est in-process et réservé aux tests d'intégration selon le contrat queue WP-2). Un binaire PyInstaller "100% Python" devrait soit embarquer un Redis (ce qui défait la promesse single-file et complique le cross-platform), soit remplacer RQ par une queue in-memory (ce qui casse l'isolation worker/API et le pattern de cancel via Redis flag). Dans les deux cas, on viole un invariant verrouillé.

- **Option C est sur-dimensionnée pour la phase 1 frontend.** Tauri produit une vraie app native, mais (1) Arthur est Python-strong / Rust-novice, (2) le frontend n'existe pas encore — on packagerait du vent, (3) la distribution `.msi/.dmg/.AppImage` n'a pas d'utilisateur cible identifié aujourd'hui (single-user, single-machine selon `CLAUDE.md`). C est la bonne réponse à une question qui n'est pas encore posée.

- **Option A reste viable mais sous-optimale.** Elle suffit pour développer, mais elle force l'utilisateur (même futur-Arthur dans 6 mois) à mémoriser `make up` puis l'URL puis le port. Pour un frontend qui doit "juste marcher", c'est une friction inutile. Le delta vers B est ~150 LOC Python.

- **Option B gagne par parcimonie.** Elle préserve **tout** ce qui marche (Docker stack, healthcheck, bind 127.0.0.1, Bearer auth, SSE, scope ML batch), ajoute une couche fine d'ergonomie, et n'introduit **aucune** nouvelle toolchain. Le coût de réversibilité est nul : si on décide plus tard de passer à Tauri (Option C) parce que le frontend devient un vrai produit distribuable, le launcher Python sera supprimé en 1 commit. Aucun invariant n'est verrouillé par ce choix.

Critère décisif pour le profil Arthur : **B est la seule option qui (a) reste 100% dans la zone de confort Python, (b) ne casse aucun invariant, (c) améliore l'UX de façon mesurable**. C est un détour, D est un cul-de-sac technique, A est un sur-place.

## Consequences

### Positives

- UX one-command pour démarrer (`python -m orchestrator.launcher` ou `make start`) avec auto-open du navigateur et health-wait — utilisable tel quel par le frontend en dev (le client peut supposer que `127.0.0.1:8000` est UP à la fin du launcher).
- Zéro nouvelle dépendance runtime (uniquement `webbrowser` stdlib + `httpx` ou `urllib` déjà tiré par FastAPI/tests).
- Le frontend (sprint suivant) peut être servi statiquement par FastAPI (mount `StaticFiles`) **ou** tourner en process séparé (Vite dev server) — le launcher reste agnostique.
- Le Makefile actuel n'est pas cassé : `make up` continue à fonctionner pour les workflows CI / scripts avancés.
- Réversibilité totale : si C ou D deviennent pertinents plus tard (distribution publique, mode offline complet), supprimer le launcher prend 10 minutes.

### Négatives / trade-offs acceptés

- **Docker Desktop reste un prérequis** sur Windows/Mac. C'est le coût de préserver la stack actuelle ; documenté dans `RUNBOOK.md`.
- Pas de "wow factor produit fini" — l'UX reste celle d'un outil dev, pas d'une app grand public. Acceptable pour single-user.
- Le launcher doit gérer proprement les états dégradés (Docker pas démarré, port 8000 occupé, healthcheck timeout). C'est ~30 LOC d'error-handling à ne pas bâcler.

### Hors-scope explicite (ce que ce choix NE règle PAS)

- Packaging distribuable (`.msi`/`.dmg`/`.AppImage`) — pas d'utilisateur cible aujourd'hui.
- Mode offline complet sans Docker — voir Option D différée si besoin futur.
- Auto-update / migration Alembic au démarrage du launcher — `make migrate` reste manuel pour l'instant.
- Choix de l'archi frontend (Vite/Next/HTMX/etc.) — sera tranché dans ADR-003 dédié au sprint frontend.
- Stratégie de bundling du frontend dans le conteneur api — décision ultérieure quand le frontend existera.

## Implementation outline

Étapes-clés pour un follow-up plan (pas une implémentation ici) :

1. Créer `src/orchestrator/launcher/__init__.py` et `__main__.py` (point d'entrée `python -m orchestrator.launcher`).
2. Implémenter `up()` : invoque `docker compose -f docker/docker-compose.yml up -d` via `subprocess.run`, capture stdout/stderr, gère le code retour.
3. Implémenter `wait_healthy(timeout=60)` : poll `GET http://127.0.0.1:8000/api/v1/health` avec backoff exponentiel, abandonne proprement si timeout (affiche `docker compose logs api`).
4. Implémenter `open_browser()` : `webbrowser.open(api_docs_url)` — désactivable via `--no-browser` pour CI/Kaggle.
   - Note 2026-06-04 : depuis ADR-003 (Accepted), `webbrowser.open` doit cibler `http://127.0.0.1:8000/` (frontend SPA) et non `/api/docs`. Garder `/api/docs` comme fallback si le bundle frontend n'est pas présent (cf. `if frontend_dist.is_dir()` dans `api/main.py`).
5. Implémenter `down()` : `docker compose down`, accessible via `python -m orchestrator.launcher --down` et `make stop`.
6. Ajouter cibles Makefile : `start` (alias `python -m orchestrator.launcher`) et `stop` (alias `--down`). Ne **pas** supprimer `up`/`down` actuels.
7. Ajouter tests unitaires (mock `subprocess.run` + mock `httpx`) — marker `unit`, coverage ≥90% sur le module (cohérent avec la gate `api/`).
8. Mettre à jour `README.md` quickstart : `make install && make token && make start` devient le triplet recommandé.
9. Mettre à jour `docs/RUNBOOK.md` section troubleshooting : port occupé, Docker non démarré, healthcheck failed.
10. Ajouter `docs/ARCHITECTURE.md` § "Launcher" pointant vers cet ADR.

## Alternatives considered (et rejetées)

- **Option A — docker-compose nu (status quo).** Rejetée car ne résout pas la friction d'entrée pour le frontend (URL/port à connaître, pas de health-wait) et le coût de B est dérisoire (~150 LOC). A reste accessible en parallèle via `make up`.
- **Option C — Tauri desktop app.** Rejetée pour la phase actuelle : toolchain Rust hors zone Python d'Arthur, distribution native sans utilisateur cible, complexité packaging multi-OS prématurée. À reconsidérer si un sprint "distribution publique" est ouvert plus tard.
- **Option D — PyInstaller + tray app avec uvicorn in-process.** Rejetée pour incompatibilité structurelle : RQ exige un Redis réel (décision verrouillée), donc D devrait soit embarquer Redis (perd la simplicité), soit remplacer RQ (casse plusieurs invariants verrouillés). Le single-binary "100% Python" promis est en réalité un fork de l'architecture.

## Invariants préservés

Décisions verrouillées de `memory/arch_orchestrator.md` qui restent valides après ce choix :

- Stack `FastAPI + SQLite + RQ + Redis` inchangée.
- Bind `127.0.0.1` + Bearer token statique inchangé (le launcher n'ouvre jamais 0.0.0.0).
- Streaming SSE inchangé.
- Scope ML batch only (collect/train/eval) inchangé.
- Pattern subprocess pour les CLI Hydra inchangé.
- Source de vérité métriques = MLflow file backend inchangée.
- Contrat Run et contrat queue (WP-1/WP-2/WP-3) inchangés.
- Règle "ne jamais modifier les 4 sibling repos" inchangée.

## References

- `memory/arch_orchestrator.md` (décisions verrouillées)
- `memory/user_profile.md` (profil Arthur)
- `docker/docker-compose.yml` (stack actuelle, healthcheck `/api/v1/health`)
- `Makefile` (commandes `make up` / `make down` / `make token`)
- `docs/ARCHITECTURE.md` (composants, data flow)
- `CLAUDE.md` (single-user, single-machine, no frontend in this repo)
