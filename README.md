# Données E-Phy pour PhytoCheck

Ce dépôt publie les données téléchargées et mises en cache par l’application PhytoCheck.

## Fichiers publiés

- `products.json` — catalogue E-Phy des produits ;
- `risk-phrases.json` — phrases de risque associées aux AMM ;
- `usages.json` — usages E-Phy autorisés ;
- `emergency-authorizations.json` — décisions temporaires d’autorisation d’urgence Article 53 du règlement (CE) n°1107/2009.

Les trois premiers fichiers proviennent des données ouvertes E-Phy / Anses. Le fichier des autorisations d’urgence est issu de la [page officielle du ministère de l’Agriculture](https://agriculture.gouv.fr/produits-phytopharmaceutiques-autorisations-de-mise-sur-le-marche-dune-duree-maximale-de-120-jours), qui publie les décisions actives et leurs PDF.

## Autorisations d’urgence Article 53

Une ligne représente une **décision** et non simplement une AMM. Une même AMM peut faire l’objet de plusieurs autorisations d’urgence simultanées, chacune limitée à une culture, une cible et une période précises.

Le collecteur conserve les décisions déjà publiées dans l’historique afin que l’application puisse signaler une expiration, même après leur retrait de la page ministérielle. La validité est toujours calculée à partir des dates officielles de délivrance et d’échéance.

La synchronisation est exécutée quotidiennement par GitHub Actions (`.github/workflows/update-emergency-authorizations.yml`) et peut aussi être lancée manuellement dans l’onglet **Actions** du dépôt.

> Les décisions PDF officielles, les conditions d’emploi et l’étiquetage applicable restent la référence. Les données publiées ici constituent une aide à la consultation dans PhytoCheck.
