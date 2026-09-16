"""Écriture des sorties intermédiaires du pipeline en JSON.

Un fichier par document source, à chaque étape (raw / clean / chunk), pour
pouvoir inspecter ce que produit chaque phase sans relancer la chaîne.
"""

import json
from pathlib import Path


def exporter_par_source(items: list, dossier: Path, suffixe: str) -> None:
    """Regroupe les Documents par fichier d'origine et écrit un JSON par source."""
    dossier.mkdir(parents=True, exist_ok=True)

    groupes: dict[str, list] = {}
    for item in items:
        nom = item.metadata.get("nom_fichier", "document_inconnu")
        groupes.setdefault(nom, []).append(item)

    for nom, elements in groupes.items():
        donnees = [
            {
                "id": f"{nom}_{suffixe}_{index}",
                "page_content": element.page_content,
                "metadata": element.metadata,
            }
            for index, element in enumerate(elements, start=1)
        ]
        chemin = dossier / f"{nom}.{suffixe}.json"
        chemin.write_text(
            json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"   -> {len(groupes)} fichier(s) JSON écrit(s) dans « {dossier} ».")


def vider_dossier(dossier: Path, motif: str) -> None:
    """Supprime les sorties de la génération précédente.

    Sans cela, un document retiré de data/raw laisse ses fichiers en place :
    l'indexation les relit à chaque passage et continue de servir aux clients
    une documentation qui n'existe plus. C'est le pendant, côté fichiers, de la
    purge effectuée en base par l'indexeur.
    """
    if not dossier.exists():
        return
    anciens = list(dossier.glob(motif))
    for fichier in anciens:
        fichier.unlink()
    if anciens:
        print(f"   -> {len(anciens)} fichier(s) de la génération précédente supprimé(s).")
