# Security

## Modèle de sécurité

RestUI est un proxy HTTP interne. Son modèle de sécurité repose sur :

- **Credentials API upstream** : lus exclusivement depuis `.env` via pydantic-settings. Le démarrage échoue si absents ou vides. Jamais dans le code source.
- **Auth utilisateur** : déléguée entièrement à Caddy (Basic Auth ou Cloudflare Access). L'application ne voit jamais de credentials utilisateur.
- **XSS** : structurellement impossible — Jinja2 auto-escape actif, aucun filtre `|safe` dans les templates.
- **Injection de filtre** : seules les colonnes explicitement déclarées `filterable: true` dans `config.yaml` sont acceptées comme paramètres URL.
- **Headers HTTP** : posés par Caddy en production (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy).

## Déploiement sécurisé

Ce projet **ne doit pas être exposé directement sur Internet** sans auth active dans Caddy. Cloudflare Tunnel seul n'est pas une barrière d'authentification.

## Signalement de vulnérabilité

Pour signaler une vulnérabilité, ouvrir une issue GitHub marquée `security` ou contacter directement via le profil GitHub.

Pas de bug bounty — projet personnel, outil interne.
