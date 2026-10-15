# Assistant SAV Electrodomus — moteur de réponse RAG

Assistant capable de répondre aux questions clients de niveau 1 (codes erreur,
entretien, garantie) **à partir de la seule documentation officielle**
d'Electrodomus : 18 manuels, 10 procédures SAV, 2 bulletins techniques,
3 FAQ, 4 documents de garantie et un référentiel de codes erreur.

Trois contraintes non négociables :

1. répondre **uniquement** à partir de la documentation, en citant document et section ;
2. **escalader** vers un conseiller plutôt qu'inventer ;
3. être exact **au modèle près** — `E23` ne signifie pas la même chose sur un
   WX-450 (pompe de vidange) et sur un LV-200 (sonde de température).

---

## Démarrage

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
copy .env.exemple .env                            # puis renseigner base et LLM

python init_db.py     # crée la base, les tables et les index (une seule fois)
python main.py        # data/raw -> data/output/{raw,clean,chunk}
python indexer.py     # embeddings BGE-M3 + chargement en base

python console.py     # l'assistant en console
python -m api        # l'assistant en API REST (http://127.0.0.1:8000/docs)
```

Ollama doit tourner avec le modèle du `.env` (`ollama pull llama3.2`), ou le
`.env` doit pointer vers une API compatible OpenAI.

### Console

```bash
python console.py "mon wx450 affiche e23"    # une question
python console.py --questions-types          # le jeu de recette (12 questions)
python console.py --passages "..."           # la recherche seule, sans LLM
python console.py --modele qwen2.5:7b "..."  # autre modèle, ponctuellement
```

### API REST

```bash
python -m api
```

Tout ce qui touche l'API est dans `api/` : `routes.py` (FastAPI), `comptes.py`,
`reglages.py`, `__main__.py` (lancement et comptes). Le moteur `rag_sav/` ne
sait rien de HTTP.

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/questions` | `{"question": "..."}` → statut, réponse, sources ; profil conseiller si identifiant + mot de passe |
| `GET` | `/sante` | base et LLM joignables ? nombre de chunks |
| `POST` | `/cache/vider` | à appeler après `python indexer.py`, sans redémarrer (conseiller) |

```bash
curl -X POST http://127.0.0.1:8000/questions \
     -H "Content-Type: application/json" \
     -d "{\"question\": \"Mon lave-linge WX-450 affiche E23\"}"
```

```json
{
  "question": "Mon lave-linge WX-450 affiche E23",
  "statut": "repondu",
  "motif": null,
  "reponse": "Le code E23 signale un défaut de la pompe de vidange. ...",
  "sources": [{"nom_fichier": "Manuel_WX-450.pdf",
               "section_path": "Manuel_WX-450 > 9. Codes erreur"}],
  "analyse": {"code": "E23", "modele": "WX-450", "gamme": "WX"},
  "profil": "client",
  "conseiller": null,
  "details": null
}
```

`reponse` est **toujours** le texte à afficher au client, quel que soit le
statut (`repondu`, `escalade`, `refus`, `non_conforme`, `erreur_llm`). Les
passages consultés et la réponse brute du modèle ne sortent jamais par défaut :
`"details": true` les renvoie à un conseiller, ou à tous si `API_DETAILS=1`
dans le `.env` (débogage). Une base injoignable rend `503`, une question vide `422`.

Réglages : `API_HOTE`, `API_PORT`, `API_ORIGINES` (CORS), `API_DETAILS`,
`FICHIER_COMPTES` — voir `.env.exemple`.

### Deux profils : client et conseiller

| | Client (sans identifiant) | Conseiller (identifiant + mot de passe) |
|---|---|---|
| Documentation interne (bulletins, procédures SAV) | lue, jamais citée | lue et citée |
| Bulletin interne qui prévaut | conduite du référentiel + « préparez le numéro de série » | le LLM répond avec le bulletin |
| Colonne « Intervention SAV (technicien) » | retirée du contexte | gardée |
| Contrôle des fuites internes | actif | sans objet |
| `details: true` | seulement si `API_DETAILS=1` | toujours |

Les règles d'escalade avant recherche (référence inconnue, code ambigu…)
s'appliquent aux deux profils.

```bash
python -m api --ajouter-conseiller jdupont     # demande le mot de passe (8 caractères mini)
python -m api --conseillers                    # liste
python -m api --supprimer-conseiller jdupont   # coupe son accès immédiatement
```

**Connexion (temporaire, en attendant le front).** HTTP Basic : identifiant et
mot de passe accompagnent chaque requête, sans étape de connexion ni jeton.
Dans `/docs`, bouton « Authorize » une fois, puis toutes les questions partent
en conseiller ; en PowerShell, `-Credential` ; en curl, `-u jdupont:motdepasse`.
Un identifiant faux rend `401` : l'API ne retombe jamais en silence sur le
profil client. Hors de la machine locale, HTTPS obligatoire. Le front web
passera à un cookie de session.

Les comptes sont dans `api/comptes_conseillers.json` (hors Git) : identifiant,
sel et empreinte PBKDF2-SHA256, jamais de mot de passe en clair. En console :
`python console.py --conseiller "..."`.

---

## Architecture

```
main.py        ingestion du corpus
init_db.py     création de la base
indexer.py     calcul des embeddings et chargement
console.py     l'assistant en console (et --passages : la recherche seule)
api/           l'assistant en API REST (python -m api)

rag_sav/
├── config.py          tous les réglages : chemins, base, seuils, LLM, API
├── catalogue.py       gammes, modèles, synonymes, détection dans le texte
├── embeddings.py      BGE-M3, chargé une seule fois
├── ingestion/
│   ├── chargeurs/     excel.py · html.py · documents.py (Docling)
│   ├── portee.py      à quel appareil un document s'applique
│   ├── cache.py       évite de reconvertir un fichier inchangé
│   ├── nettoyage.py   nettoyage du texte extrait
│   ├── chunking.py    découpage en chunks
│   └── export.py      sorties JSON intermédiaires
├── stockage/
│   ├── schema.py      tables, pgvector, index GIN et HNSW
│   ├── connexion.py   connexions refermées quoi qu'il arrive
│   └── indexer.py     indexation + purge des documents retirés
├── recherche/
│   ├── analyse.py     comprendre la question
│   ├── escalade.py    règles déterministes de refus, AVANT de chercher
│   ├── requete.py     SQL hybride + filtre dur
│   └── resultats.py   mise en forme + diagnostic
└── generation/
    ├── __init__.py    repondre() : enchaîne tout le reste
    ├── verrou.py      refus APRÈS avoir cherché : contexte exploitable ?
    ├── referentiel.py réponse tirée du référentiel (repli si le LLM échoue)
    ├── prompt.py      règles de rédaction + passages numérotés
    ├── llm.py         Ollama ou compatible OpenAI, essais et modèles de secours
    └── controle.py    citations et fuites de contenu interne vérifiées
```

**Chaîne de traitement**

```
data/raw → chargeurs → nettoyage → chunking → embeddings → PostgreSQL
                                                                 ↓
question → analyse → escalade ? → recherche filtrée → verrou ? → prompt
         → LLM → contrôle → réponse (console ou API)
```

---

## Pourquoi une métadonnée et pas du texte

C'est le point central du projet. L'exactitude au modèle près **ne peut venir
ni de la recherche plein texte, ni de la recherche sémantique.**

### La recherche plein texte ne peut pas trancher

La première version construisait la requête `e23 & lv & 200`. Or PostgreSQL
n'indexe pas `LV-200` comme `lv` et `200` :

```sql
SELECT to_tsvector('french', 'LV-200');
   '-200':2 'lv':1          -- le nombre est indexé AVEC le tiret

SELECT to_tsvector('french','LV-200') @@ to_tsquery('french','lv & 200');
   f                        -- ne correspond jamais
```

Le lexème `200` n'existait quasiment nulle part dans l'index (1 occurrence,
contre 66 pour `-200`). Résultat : **toute question associant un modèle et un
code renvoyait 0 résultat côté texte**, et basculait silencieusement sur la
seule branche vectorielle — sans aucune contrainte de modèle.

### La recherche sémantique ne peut pas trancher non plus

Sur 875 chunks, **529 (60 %) sont le doublon exact** d'un passage figurant
dans un autre document ; certains paragraphes existent en 18 exemplaires, à
travers les lave-linge, les lave-vaisselle *et* les fours. Seul le préfixe
diffère — quelques caractères sur plus de quatre cents. Les vecteurs produits
sont quasi confondus : le classement sémantique entre gammes relève du hasard.

### Donc : une métadonnée, et un filtre qui exclut

Chaque document reçoit une **portée** dérivée de son nom ou de son contenu :

| Document | portée | couvre |
|---|---|---|
| `Manuel_WX-450.pdf` | `modele` | WX-450 |
| `PROC-WX-01_Detartrage.docx` | `gamme` | les 6 modèles WX |
| `BT-2026-007.docx` | `modele` | WX-500 *(lu dans le contenu)* |
| `CGV_Electrodomus.pdf` | `global` | tout |

La déduction par le **contenu** (dernière ligne du tableau) est réservée aux
bulletins techniques — `CATEGORIES_PORTEE_PAR_CONTENU` dans `portee.py`. Le
jour où le CGV cite « WX-450 » en exemple, il deviendrait sinon un document
WX-450 et disparaîtrait des recherches de tous les autres appareils, alors
qu'il est le seul à répondre aux questions de garantie.

La recherche applique alors un **filtre dur**, identique sur les deux branches :

```sql
WHERE metadata->'modeles_couverts' @> to_jsonb('WX-450'::text)
   OR metadata->>'portee' = 'global'
```

C'est une **exclusion**, pas un critère de classement : un classement remonte
les bons passages mais ne retire jamais les mauvais. Concrètement, l'espace de
recherche passe de 875 chunks à 116 pour un WX-450 — 87 % du bruit éliminé
avant même que la recherche commence.

---

## Performance de l'ingestion

L'étape la plus coûteuse du pipeline est la conversion des 22 PDF par Docling :
un modèle de mise en page tourne sur chaque page, plus un modèle de
reconnaissance de tableaux sur chaque tableau détecté. Sur un poste sans carte
graphique, cela représente plusieurs minutes.

**L'OCR n'y est pour rien** : il est désactivé (`do_ocr = False`), le corpus
étant composé de PDF nativement textuels. Trois leviers agissent réellement :

| Levier | Effet |
|---|---|
| **Cache de conversion** | Un fichier inchangé n'est jamais reconverti. Un relancement passe de plusieurs minutes à quelques secondes. |
| **`MODE_TABLEAUX=fast`** | Modèle de tableaux rapide. Les grilles de codes erreur du corpus sont simples, le mode précis n'y apporte rien. |
| **`NB_THREADS_DOCLING`** | Threads alloués à Docling. Par défaut, le nombre de cœurs. |

```bash
python main.py                  # les fichiers inchangés sortent du cache
python main.py --vider-cache    # force la reconversion complète
```

Le cache vit dans `data/output/.cache_conversion/`, indexé sur
(chemin, date de modification, taille). Modifier un document source suffit à
l'invalider. Ce n'est qu'une accélération : le supprimer ne change aucun
résultat.

> Au **tout premier** lancement, Docling télécharge ses modèles (plusieurs
> centaines de Mo). Ce téléchargement est fait une fois pour toutes ; si le
> pipeline semble figé au démarrage, c'est probablement lui.

---

## Reconnaître ce que le client écrit

Un client n'écrit pas `WX-450` et `E23`. Il écrit `wx450`, `WX 450`, `wx_450`,
`WX–450` (tiret inséré par Word), `e 23`, `E-023`. La détection ne repose donc
pas sur une expression régulière unique de plus en plus dense, mais sur trois
temps (`rag_sav/catalogue.py`) :

1. **Normaliser** — minuscules, accents retirés, tirets typographiques et
   espaces exotiques ramenés à leurs équivalents ASCII. Les motifs n'ont plus à
   énumérer les variantes d'écriture.
2. **Extraire** — un motif volontairement permissif remonte des *candidats* :
   deux lettres + 3-4 chiffres pour une référence, `E`/`F` + 1-3 chiffres pour
   un code, séparés par rien, un tiret, un souligné, un point, une barre ou
   des espaces.
3. **Valider** — chaque candidat est confronté au catalogue. `E023` et `E23`
   sont ramenés au même code ; `BT-2026` est écarté (préfixe inconnu) ;
   `WX-460` est conservé **à part**, comme référence inconnue.

Élargir la tolérance revient à toucher la normalisation ou la liste de
séparateurs, pas à récrire un motif.

**Deux garde-fous**, car « souple » ne doit pas vouloir dire « devinatoire » :

- un code séparé par un espace est refusé après un mot de numérotation
  (`annexe E 23`, `figure F 12`) et exige au moins deux chiffres ;
- un numéro donné seul (`mon lave-linge 450`) n'est résolu que si la gamme est
  dite en clair par ailleurs, que le numéro existe dans cette gamme, et qu'il
  n'est ni précédé d'un mot de numérotation (`page 450`, `commande n° 450`) ni
  suivi d'une unité (`450 euros`, `450 tr/min`). L'origine est tracée dans
  `analyse["origine_modele"]`.

Vérification : `python tests/test_detection.py` (aucune dépendance) — et rejeu
des deux jeux de motifs, ancien et nouveau, sur les 420 chunks du corpus :
**aucune différence de détection**, donc aucun faux positif introduit.

---

## Escalade

Déterministe, sans aucun score — donc reproductible et auditable
(`rag_sav/recherche/escalade.py`) :

| Situation | Décision |
|---|---|
| Plusieurs appareils cités | Demander lequel |
| Référence bien formée mais hors catalogue (`WX-460`) | Le dire, et demander de vérifier l'étiquette |
| Code inconnu de toute la documentation (`F12`) | Le dire, et transmettre à un conseiller |
| Code connu, mais absent de la documentation de l'appareil (`E15` sur un WX-450) | Demander de vérifier code et référence |
| Code ambigu sans appareil identifié | Demander la référence, en nommant les gammes |
| Code sans appareil identifié, même non ambigu (`E77`) | Demander la référence |

Les codes ambigus ne sont **pas écrits en dur** : ils sont déduits du
référentiel tel qu'il est indexé (un code présent dans plusieurs gammes). Un
référentiel mis à jour fait suivre l'escalade automatiquement. Aujourd'hui :
`E01`, `E10`, `E23`, `E31`, `E42`.

Un code est déclaré **inconnu** seulement s'il n'apparaît ni dans le
référentiel, ni dans le texte d'aucun chunk : `E52` n'est traité que par le
bulletin BT-2026-007, il ne doit pas déclencher d'escalade pour autant.

La règle **code hors appareil** (14/10) cherche le code dans la documentation
*visible pour cet appareil*, avec la même clause que le filtre dur. Mesure du
12/10 sur les 252 couples modèle × code : les 132 codes d'une autre gamme sont
absents de toute cette documentation, les 120 codes de la gamme y sont tous.
Avant cette règle, « Mon WX-450 affiche E15 » appelait le LLM avec cinq
passages qui ne parlent pas de E15.

> **Ces règles tiennent lieu de « cross-vérification des métadonnées »** du
> schéma d'architecture. Ce bloc avait été dessiné quand la contrainte modèle
> était un critère de classement ; depuis, le filtre dur exclut en SQL *avant*
> la fusion, et `correspondance_modele` mesure déjà le rattachement de chaque
> passage. Ce que le filtre ne peut pas garantir, c'est le cas où il n'a rien
> à filtrer — un code posé sans appareil, ou un code que personne ne
> documente. C'est ce trou que ferment les deux dernières règles.

Vérification : `python tests/test_escalade.py` — 15 cas sur référentiel simulé,
donc aucune base requise. Ce sont les **règles** qui sont testées, pas le SQL :
les deux requêtes de `escalade.py` restent à valider sur la base réelle.

---

## Confiance

L'ancien « score de confiance » normalisait le score RRF par son maximum
théorique. Dès que la branche plein texte était vide — c'est-à-dire sur toutes
les questions « modèle + code » — il plafonnait à **52,9 %**, quelle que soit
la qualité de la réponse. Inutilisable comme seuil.

Il est remplacé par trois indicateurs honnêtes :

- `similarite` — similarité cosinus réelle dans [0, 1], comparable d'une
  question à l'autre ;
- `correspondance_modele` — `exacte` / `gamme` / `transverse` / `non_contrainte` ;
- `diagnostic.contexte_faible` — le meilleur passage est-il vraiment proche ?

> Le seuil `SEUIL_SIMILARITE_PROVISOIRE` de `config.py` est une **valeur
> d'attente**. Il doit être calibré sur le jeu d'évaluation, pas deviné.

---

## Priorité documentaire

Les bulletins techniques prévalent explicitement sur les manuels et le
référentiel : *« Ce bulletin prévaut sur la documentation produit antérieure
pour les points qu'il traite »* (BT-2026-011). Un bulletin est donc remonté en
tête — mais **seulement s'il concerne le code demandé**, pour éviter qu'un
bulletin hors sujet passe devant.

Ces documents portent la mention « documentation interne » et citent des
références de pièces. Règle retenue : **l'assistant les lit, mais ne les cite
pas** à un client, et `controle.py` écarte toute réponse qui cite un document
interne ou reprend un de ses marqueurs chiffrés.

Quand un bulletin interne prévaut pour le code et l'appareil demandés, le LLM
n'est pas appelé : le client lit la conduite à tenir du référentiel (les deux
bulletins du corpus ne changent que l'intervention technicien), présentée
comme une signification « référencée », avec l'invitation à préparer son
numéro de série pour le conseiller (`motif = referentiel_sous_bulletin`,
14/10). Sans ligne de référentiel pour ce couple, un conseiller reprend la main
(`bulletin_prevaut`, 12/10).

---

## Le moteur de réponse

`repondre()` (`rag_sav/generation/__init__.py`) rend toujours l'un de cinq
statuts. Un seul laisse le client lire le texte du modèle :

| Statut | Décidé par | Le LLM a-t-il tourné ? |
|---|---|---|
| `escalade` | `escalade.py` (avant recherche) ou `verrou.py` (`bulletin_prevaut` sans ligne de référentiel) | non |
| `refus` | `verrou.py` : rien trouvé, rien de rattaché à l'appareil, contexte trop éloigné, rien de citable | non |
| `erreur_llm` | `llm.py` : panne, délai, quota — après essais et modèles de secours | tenté |
| `non_conforme` | `controle.py` : citation inventée, citation interne, fuite interne | oui, réponse écartée |
| `repondu` | `controle.py` : aucun défaut | oui |

Quand le modèle échoue ou répond hors des règles alors que le référentiel
couvre le couple code + appareil, le client lit la « conduite à tenir » du
référentiel (`motif = repli_referentiel`) plutôt qu'un renvoi au conseiller.

---

## État d'avancement

| Étape | État |
|---|---|
| Métadonnées `modele` / `gamme` / `portee` | fait |
| Référentiel Excel découpé ligne par ligne | fait |
| Filtre dur sur le modèle | fait |
| Escalade déterministe + confiance honnête | fait |
| Détection souple des références et des codes | fait |
| Portée, nettoyage, imports paresseux | fait |
| Moteur de réponse (verrou, prompt, LLM, contrôle, repli) | fait |
| Contenu interne : bulletin qui prévaut → conseiller, fuites détectées | fait (12/10) |
| Escalade « code hors appareil » | fait (14/10) |
| Bulletin qui prévaut : conduite client du référentiel au lieu d'une escalade muette | fait (14/10) |
| Comptes conseillers : documentation interne citable | fait (14/10) |
| API REST | fait (14/10) |

### Tests

14 suites, **135 tests**, sans base, sans LLM, sans réseau :

```bash
pytest tests/                    # ou chaque fichier : python tests/test_api.py
```

| Suite | Ce qu'elle garde |
|---|---|
| `test_detection` | références et codes erreur dans le texte libre |
| `test_escalade` | les 6 règles et leur ordre, référentiel simulé |
| `test_ingestion` | portée documentaire et nettoyage |
| `test_imports` | la logique s'importe sans psycopg2, torch ni Docling |
| `test_verrou` | refus après recherche, bulletin qui prévaut |
| `test_prompt` | passages, drapeaux, colonne technicien retirée |
| `test_controle` | citations inventées / internes, fuites chiffrées |
| `test_referentiel` | réponse tirée du référentiel |
| `test_repli` | repli référentiel quand le modèle échoue |
| `test_llm_secours` | essais, modèles de secours, réponses vides ou coupées |
| `test_config` | lecture du seuil de similarité |
| `test_api` | contrat HTTP : rien d'interne ne sort, 403 / 422 / 503, profils |
| `test_comptes` | mots de passe hachés, vérification, suppression |
| `test_conseiller` | profil conseiller : bulletin cité, colonne technicien gardée |

Non couverts par les tests : le SQL lui-même et le chunking. Ils se vérifient
sur la base réelle avec `python console.py --questions-types`.

### Points ouverts

1. **Calibrer `SEUIL_SIMILARITE`** (0.45 provisoire) sur des questions réelles,
   avec les vrais embeddings BGE-M3.
2. **Choisir le modèle** : `llama3.2` (3B) est le défaut ; le comparer à un
   modèle plus gros avec `--modele`.
3. Le contrôle des fuites porte sur les chiffres : une reformulation sans
   chiffre d'une procédure interne passe encore.
4. Un seul code erreur est retenu par question (le premier cité).
5. Une gamme absente du catalogue (`SL-900`) n'est pas reconnue.
