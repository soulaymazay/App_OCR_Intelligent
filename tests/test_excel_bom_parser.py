#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_excel_bom_parser.py - Groupe Bayoudh Metal

Script de test pour vérifier l'extraction Excel BOM.
Ce script simule l'extraction d'un fichier Excel de nomenclature.

USAGE:
    cd /home/soulaymazay/frappe-bench
    bench --site ocr.localhost execute apps/ocr_intelligent/tests/test_excel_bom_parser.py
    
    OU depuis Python:
    
    python3 apps/ocr_intelligent/tests/test_excel_bom_parser.py /chemin/vers/bom.xlsx
"""

import sys
import os

# Ajouter le chemin des modules
sys.path.insert(0, '/home/soulaymazay/frappe-bench/apps/ocr_intelligent')

from ocr_intelligent.ocr.excel_bom_parser import extraire_bom_depuis_excel


def test_excel_bom(chemin_fichier=None):
    """Test d'extraction Excel BOM"""
    
    if not chemin_fichier:
        print("❌ Usage: python3 test_excel_bom_parser.py /chemin/vers/fichier.xlsx")
        return False
    
    if not os.path.exists(chemin_fichier):
        print(f"❌ Fichier introuvable : {chemin_fichier}")
        return False
    
    print(f"\n{'='*70}")
    print(f"TEST EXTRACTION EXCEL BOM")
    print(f"{'='*70}")
    print(f"Fichier : {chemin_fichier}")
    print(f"{'='*70}\n")
    
    try:
        # Extraction
        resultat = extraire_bom_depuis_excel(chemin_fichier)
        
        # Affichage résultats
        print(f"✅ Type document : {resultat.get('type_document', 'inconnu')}")
        print(f"✅ Nombre de champs header : {len(resultat.get('champs', {}))}")
        print(f"✅ Nombre de composants : {resultat.get('nb_composants', 0)}")
        
        if resultat.get('erreur'):
            print(f"\n⚠️  ERREUR : {resultat['erreur']}")
            return False
        
        # Détails champs header
        print(f"\n{'─'*70}")
        print("CHAMPS HEADER EXTRAITS :")
        print(f"{'─'*70}")
        for champ, valeur in resultat.get('champs', {}).items():
            conf = resultat.get('confiances', {}).get(champ, 1.0)
            print(f"  • {champ:25} = {valeur!s:30} (conf: {conf:.2f})")
        
        # Détails composants
        composants = resultat.get('composants', [])
        if composants:
            print(f"\n{'─'*70}")
            print(f"COMPOSANTS EXTRAITS ({len(composants)}) :")
            print(f"{'─'*70}")
            print(f"{'#':>3} | {'Code':12} | {'Nom':30} | {'Qté':>8} | {'UdM':6} | {'Prix':>10}")
            print(f"{'-'*3}-+-{'-'*12}-+-{'-'*30}-+-{'-'*8}-+-{'-'*6}-+-{'-'*10}")
            
            for i, comp in enumerate(composants, 1):
                code = comp.get('item_code', '')[:12]
                name = comp.get('item_name', '')[:30]
                qty = comp.get('qty', 0)
                uom = comp.get('uom', '')[:6]
                rate = comp.get('rate', 0)
                warn = '⚠' if comp.get('item_exists') == False else ' '
                
                print(f"{i:3} | {warn}{code:11} | {name:30} | {qty:8.3f} | {uom:6} | {rate:10.3f}")
        else:
            print("\n⚠️  AUCUN COMPOSANT DÉTECTÉ")
            print("     Vérifiez que votre Excel contient :")
            print("     • Une ligne d'en-têtes : Code Article, Nom Article, Quantité, UdM")
            print("     • Au moins une ligne de données sous les en-têtes")
        
        print(f"\n{'='*70}")
        if composants:
            print("✅ TEST RÉUSSI")
        else:
            print("⚠️  TEST PARTIEL (champs header OK, mais 0 composants)")
        print(f"{'='*70}\n")
        
        return len(composants) > 0
    
    except Exception as e:
        print(f"\n❌ ERREUR EXCEPTION : {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n" + "="*70)
        print("TEST EXTRACTION EXCEL BOM - Groupe Bayoudh Metal")
        print("="*70)
        print("\nUSAGE:")
        print("  python3 tests/test_excel_bom_parser.py /chemin/vers/fichier.xlsx")
        print("\nEXEMPLE:")
        print("  python3 tests/test_excel_bom_parser.py sites/ocr.localhost/private/files/BOM-0004-001.xlsx")
        print("\n" + "="*70 + "\n")
        sys.exit(1)
    
    fichier = sys.argv[1]
    success = test_excel_bom(fichier)
    sys.exit(0 if success else 1)
