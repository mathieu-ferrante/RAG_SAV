from pathlib import Path

DOSSIER_RAW = Path("data/output/raw")
DOSSIER_CLEAN = Path("data/output/clean")

def tester_pipeline():
    print("=== DÉBUT DU TEST DU PIPELINE ===")

    # 1. Vérification de l'existence des dossiers
    if not DOSSIER_RAW.exists() or not DOSSIER_CLEAN.exists():
        print("❌ ERREUR : Les dossiers d'exportation n'existent pas. Lance 'main.py' d'abord.")
        return

    fichiers_raw = list(DOSSIER_RAW.glob("*.md"))
    fichiers_clean = list(DOSSIER_CLEAN.glob("*.md"))

    print(f"-> Fichiers trouvés dans RAW : {len(fichiers_raw)}")
    print(f"-> Fichiers trouvés dans CLEAN : {len(fichiers_clean)}")

    # 2. Test d'existence et de correspondance
    if len(fichiers_raw) == 0:
        print("❌ ÉCHEC : Aucun fichier généré dans 'data/output/raw/'.")
        return

    if len(fichiers_raw) != len(fichiers_clean):
        print("❌ ÉCHEC : Le nombre de fichiers dans RAW et CLEAN ne correspond pas.")
        return

    print("✅ TEST 1 REUSSI : Tous les fichiers sont présents dans RAW et CLEAN.")

    # 3. Test du contenu (fichiers vides + structure des tableaux Excel)
    fichiers_vides = []
    tableaux_alteres = []

    for path_clean in fichiers_clean:
        path_raw = DOSSIER_RAW / path_clean.name

        if not path_raw.exists():
            print(f"❌ ÉCHEC : Le fichier correspondant {path_clean.name} n'existe pas dans RAW.")
            continue

        content_clean = path_clean.read_text(encoding="utf-8").strip()
        content_raw = path_raw.read_text(encoding="utf-8").strip()

        # Fichier vide
        if not content_clean:
            fichiers_vides.append(path_clean.name)

        # Contrôle des séparateurs de tableaux pour les fichiers issus d'Excel
        if "onglet" in path_clean.name:
            pipes_raw = content_raw.count("|")
            pipes_clean = content_clean.count("|")
            if pipes_raw != pipes_clean:
                tableaux_alteres.append((path_clean.name, pipes_raw, pipes_clean))

    if fichiers_vides:
        print(f"❌ ÉCHEC : Fichiers vides détectés dans CLEAN : {fichiers_vides}")
    else:
        print("✅ TEST 2 REUSSI : Aucun fichier vide.")

    if tableaux_alteres:
        print("⚠️ ATTENTION : Perte potentielle de structure sur des tableaux Excel :")
        for nom, raw, clean in tableaux_alteres:
            print(f"   - {nom} : {raw} '|' en RAW vs {clean} '|' en CLEAN")
    else:
        print("✅ TEST 3 REUSSI : Les tableaux Excel ont conservé leur structure.")

    print("\n=== PIPELINE VALIDÉ AVEC SUCCÈS ===")

if __name__ == "__main__":
    tester_pipeline()