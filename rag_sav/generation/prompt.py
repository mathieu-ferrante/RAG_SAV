"""Construction du prompt : là où les contraintes client deviennent du texte.

Trois des règles du projet ne peuvent PAS être portées par du SQL. Elles sont
ici, et nulle part ailleurs :

  1. Ne répondre qu'à partir des passages fournis, et citer document + section.
  2. Lire la documentation interne sans jamais la citer (décision du 15/09) :
     un bulletin technique dit la vérité la plus à jour, mais il cite des
     références de pièces et s'adresse à un technicien.
  3. Refuser plutôt que d'extrapoler quand le contexte ne couvre pas
     exactement l'appareil du client.

Le prompt *demande*. Il ne garantit rien : c'est `controle.py` qui vérifie
après coup, de façon déterministe. Un prompt est une consigne, pas un verrou —
confondre les deux est l'erreur classique du RAG.
"""

import re

from rag_sav.catalogue import libelle_gamme

# La ligne du référentiel destinée au technicien (références de pièces). Elle
# s'arrête à la puce suivante, à la ligne de version en italique ou à la fin.
MOTIF_CHAMP_TECHNICIEN = re.compile(
    r"\n?- \*\*Intervention SAV \(technicien\) :\*\*.*?(?=\n- \*\*|\n\*[^*]|\Z)",
    re.S,
)

SYSTEME = """Tu es l'assistant du service après-vente d'Electrodomus, fabricant \
de lave-linge (gamme WX), lave-vaisselle (gamme LV) et fours encastrables \
(gamme FR). Tu réponds à un client particulier.

RÈGLES ABSOLUES, dans cet ordre de priorité :

1. FONDER. Tu réponds EXCLUSIVEMENT avec le contenu des passages numérotés \
fournis ci-dessous. Tu n'ajoutes aucune connaissance générale sur \
l'électroménager, aucune cause probable, aucune manipulation qui ne soit pas \
écrite dans un passage. Si les passages ne suffisent pas, tu le dis et tu \
proposes un conseiller.

2. CITER. Tu termines toujours par un bloc « Sources : », une ligne par \
passage réellement utilisé. Chaque ligne est un tiret suivi de la ligne \
« SOURCE AUTORISÉE » du passage, RECOPIÉE CARACTÈRE POUR CARACTÈRE — accents, \
tirets et extension du fichier compris. Tu n'écris jamais autre chose dans ce \
bloc, tu n'inventes aucun nom de fichier et tu ne cites aucun document qui ne \
figure pas dans la liste des sources autorisées.

3. NE PAS CITER L'INTERNE. Un passage marqué [INTERNE] est de la documentation \
technique destinée à nos techniciens. Tu peux t'en servir pour être exact — \
notamment quand il est marqué [FAIT AUTORITÉ] — mais tu ne le cites JAMAIS \
dans le bloc « Sources : », tu ne mentionnes ni son nom, ni une référence de \
pièce, ni une consigne réservée au technicien. Si ce que tu veux dire ne \
s'appuie que sur de l'interne, dis plutôt que le diagnostic demande \
l'intervention d'un conseiller.

4. RESTER SUR L'APPAREIL. Un même code erreur n'a pas le même sens selon \
l'appareil. Tu ne transposes jamais une procédure d'une gamme à une autre. Si \
les passages ne traitent pas l'appareil indiqué, tu refuses de répondre.

5. AUTORITÉ. Un passage marqué [FAIT AUTORITÉ] est un bulletin technique \
récent : il prévaut sur un manuel ou sur le référentiel pour ce qu'il traite.

FORME : vouvoiement, ton de SAV, direct. Les passages sont ta matière \
première, pas ta réponse : tu les reformules, tu ne les recopies pas et tu ne \
les énumères pas. Le client ne doit jamais avoir à lire la documentation pour \
comprendre ce que tu lui dis.

Tu commences par LA RÉPONSE, en une ou deux phrases : ce qui se passe sur son \
appareil, puis ce qu'il doit faire maintenant. Si plusieurs manipulations sont \
nécessaires, tu les détailles ensuite, numérotées, dans l'ordre où il doit les \
faire. Pas de formule d'accueil, pas de résumé de la question. Dix lignes au \
plus, puis le bloc « Sources : »."""


# Profil « conseiller » (API avec compte, console --conseiller) : la même
# rigueur de citation, mais toute la documentation est citable et la réponse
# s'adresse à un professionnel. Les règles 1, 2 et 4 du client sont reprises
# mot pour mot : seules changent la cible et la place de l'interne.
SYSTEME_CONSEILLER = """Tu es l'assistant interne du service après-vente \
d'Electrodomus, fabricant de lave-linge (gamme WX), lave-vaisselle (gamme LV) \
et fours encastrables (gamme FR). Tu réponds à un CONSEILLER SAV, pas au client.

RÈGLES ABSOLUES, dans cet ordre de priorité :

1. FONDER. Tu réponds EXCLUSIVEMENT avec le contenu des passages numérotés \
fournis ci-dessous. Tu n'ajoutes aucune connaissance générale sur \
l'électroménager, aucune cause probable, aucune manipulation qui ne soit pas \
écrite dans un passage. Si les passages ne suffisent pas, tu le dis.

2. CITER. Tu termines toujours par un bloc « Sources : », une ligne par \
passage réellement utilisé. Chaque ligne est un tiret suivi de la ligne \
« SOURCE AUTORISÉE » du passage, RECOPIÉE CARACTÈRE POUR CARACTÈRE — accents, \
tirets et extension du fichier compris. Tu n'inventes aucun nom de fichier. \
La documentation interne (bulletins, procédures SAV) se cite comme le reste.

3. AUTORITÉ. Un passage marqué [FAIT AUTORITÉ] est un bulletin technique \
récent : il prévaut sur un manuel ou sur le référentiel pour ce qu'il traite. \
Quand il change la conduite à tenir, donne la conduite du bulletin et signale \
que le manuel ou le référentiel est dépassé sur ce point.

4. RESTER SUR L'APPAREIL. Un même code erreur n'a pas le même sens selon \
l'appareil. Tu ne transposes jamais une procédure d'une gamme à une autre.

5. DISTINGUER. Sépare ce que le conseiller dit ou fait faire au client de ce \
qui relève du technicien (contrôles, références de pièces).

FORME : style de note interne, direct, sans formule d'accueil. Commence par \
la conduite à tenir en une ou deux phrases. Puis, si utile, « Côté client : » \
et « Côté technicien : », chacun en étapes numérotées. Quinze lignes au plus, \
puis le bloc « Sources : »."""


CONSIGNE_PLUSIEURS_GAMMES = """

CONSIGNE PARTICULIÈRE : le client n'a pas indiqué son appareil, et les passages \
relèvent de plusieurs gammes ({gammes}). Si la réponse est la même pour toutes, \
dis-le dans ta première phrase (« Pour tous nos appareils, … »). Sinon, réponds \
gamme par gamme en nommant chaque gamme (lave-linge WX, lave-vaisselle LV, \
four FR), sans jamais appliquer à une gamme ce qui est écrit pour une autre. \
Termine par une phrase invitant le client à donner la référence de son appareil \
(étiquette signalétique) pour une réponse précise."""


# Les petits modèles locaux (1 à 3 milliards de paramètres) perdent la consigne
# du début quand le contexte est long : on la répète en toute fin de message.
RAPPEL_APPAREIL_VERIFIE = """

Les passages ci-dessus ont déjà été vérifiés : ils concernent bien l'appareil \
du client. Ne refuse donc pas de répondre pour une raison d'appareil ou de \
code : réponds avec ce qu'ils disent."""

RAPPEL_FINAL = """

RAPPEL : réponse en français, la réponse d'abord, puis le bloc « Sources : » \
avec les lignes autorisées recopiées telles quelles."""


def corps_du_passage(passage: str, garder_technicien: bool = False) -> str:
    """Retire l'en-tête injecté à l'ingestion (Document / Appareil / Section).

    Il est utile en base — il rend les 60 % de chunks dupliqués un peu moins
    confondables pour l'embedding — mais le répéter ici doublerait une
    information que l'en-tête numéroté ci-dessous donne déjà, en plus propre.

    On ne coupe QUE si l'en-tête est bien là : sur un chunk sans en-tête, un
    `split` aveugle mangerait le premier paragraphe.
    """
    # Le LLM rédige désormais lui-même la réponse tirée du référentiel : la
    # colonne technicien (références de pièces) ne doit même pas entrer dans
    # son contexte. `controle.py` reste là pour vérifier, mais mieux vaut ne
    # pas lui laisser de quoi s'égarer.
    if not garder_technicien:
        passage = MOTIF_CHAMP_TECHNICIEN.sub("", passage)
    if not passage.startswith("Document:"):
        return passage.strip()
    _, separateur, reste = passage.partition("\n\n")
    return (reste if separateur else passage).strip()


def _drapeaux(resultat: dict, appareil: str | None) -> str:
    marques = []

    if resultat.get("audience_origine", "client") != "client":
        # Profil conseiller : l'interne est citable, mais il reste signalé.
        marques.append("documentation INTERNE (conseillers, techniciens)")
    elif resultat.get("audience") == "client":
        marques.append("document client")
    else:
        marques.append("INTERNE — à lire, jamais à citer")

    correspondance = resultat.get("correspondance_modele")
    if correspondance == "exacte" and appareil:
        marques.append(f"propre à {appareil}")
    elif correspondance == "gamme":
        couverts = resultat.get("modeles_couverts") or []
        marques.append(f"vaut pour {', '.join(couverts) or 'la gamme'}")
    elif correspondance == "transverse":
        marques.append("document transverse")

    if resultat.get("prevaut"):
        marques.append("FAIT AUTORITÉ")

    return " · ".join(marques)


def sources_autorisees(passages: list[dict]) -> list[str]:
    """Les lignes de citation que le modèle a le droit de recopier.

    Liste FERMÉE : un passage interne n'y figure pas, puisqu'il ne se cite
    jamais. Le modèle n'a donc plus à déduire ce qu'il peut citer — il choisit
    dans une liste, ce qu'un petit modèle sait faire bien mieux que suivre une
    consigne négative.
    """
    return [
        f"{r['nom_fichier']} — {r['section_path']}"
        for r in passages
        if r.get("audience", "client") == "client"
    ]


def formater_contexte(
    passages: list[dict], appareil: str | None = None, conseiller: bool = False
) -> str:
    """Les passages, numérotés, avec l'en-tête que le LLM doit recopier."""
    blocs = []
    for numero, resultat in enumerate(passages, start=1):
        # Seule une source client est « autorisée » : l'étiquette doit dire la
        # même chose que la liste fermée des sources autorisées, sans quoi un
        # petit modèle recopie la ligne d'un passage interne dans « Sources : ».
        etiquette = (
            "SOURCE AUTORISÉE"
            if resultat.get("audience", "client") == "client"
            else "SOURCE INTERNE, NON CITABLE"
        )
        blocs.append(
            f"[{numero}] {etiquette} : "
            f"{resultat['nom_fichier']} — {resultat['section_path']}\n"
            f"({_drapeaux(resultat, appareil)})\n"
            f"{corps_du_passage(resultat['page_content'], garder_technicien=conseiller)}"
        )
    return "\n\n---\n\n".join(blocs)


def _appareil(analyse: dict) -> str | None:
    if analyse.get("modele"):
        return f"{libelle_gamme(analyse['gamme'])} {analyse['modele']}"
    if analyse.get("gamme"):
        return f"{libelle_gamme(analyse['gamme'])} (gamme {analyse['gamme']}, modèle non précisé)"
    return None


def construire(
    question: str, passages: list[dict], analyse: dict, profil: str = "client"
) -> list[dict]:
    """Les deux messages envoyés au modèle.

    L'appareil et le code sont répétés en clair dans le message utilisateur :
    ils sont déjà dans la question, mais la détection les a canonicalisés
    (« wx450 » -> « WX-450 », « e 023 » -> « E23 ») et c'est cette forme-là
    qui figure dans les passages. Donner les deux évite au modèle d'avoir à
    faire le rapprochement lui-même.
    """
    appareil = _appareil(analyse)
    autorisees = sources_autorisees(passages)

    gammes = sorted({p["gamme"] for p in passages if p.get("gamme")})
    plusieurs_gammes = not analyse.get("modele") and not analyse.get("gamme") and len(gammes) > 1

    conseiller = profil == "conseiller"
    entete = [f"Question du {'conseiller' if conseiller else 'client'} : {question}"]
    if appareil:
        entete.append(f"Appareil identifié : {appareil}")
    else:
        entete.append("Appareil : non identifié.")
    if analyse.get("code"):
        entete.append(f"Code erreur identifié : {analyse['code']}")

    utilisateur = (
        "\n".join(entete)
        + "\n\nPASSAGES DE LA DOCUMENTATION :\n\n"
        + formater_contexte(passages, appareil, conseiller)
        + "\n\n---\n\nSOURCES AUTORISÉES — tu ne peux citer que ces lignes, "
        + "recopiées exactement :\n"
        + ("\n".join(f"- {ligne}" for ligne in autorisees) or "- (aucune)")
        + f"\n\nRéponds au {'conseiller' if conseiller else 'client'} en appliquant les règles absolues."
        + (CONSIGNE_PLUSIEURS_GAMMES.format(gammes=", ".join(gammes)) if plusieurs_gammes else "")
        + (RAPPEL_APPAREIL_VERIFIE if appareil and analyse.get("modele") else "")
        + RAPPEL_FINAL
    )

    return [
        {"role": "system", "content": SYSTEME_CONSEILLER if conseiller else SYSTEME},
        {"role": "user", "content": utilisateur},
    ]
