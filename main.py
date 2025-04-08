#!/usr/bin/env python3
"""
DShorts - Prototype Local
-------------------------------
Version améliorée du script principal pour la génération de shorts.
"""

import os
import sys
import argparse
import time
import logging
from pathlib import Path
from colorama import init, Fore, Style

# Initialiser colorama pour les couleurs de terminal
init()

# Import des modules DShorts
from dshorts.video_analyzer import VideoAnalyzer
from dshorts.audio_analyzer import AudioAnalyzer
from dshorts.text_analyzer import TextAnalyzer  
from dshorts.clip_generator import ClipGenerator

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Analyser les arguments de ligne de commande"""
    parser = argparse.ArgumentParser(description="DShorts - Générer des vidéos courtes à partir de vidéos longues (Version améliorée)")
    parser.add_argument("video_path", help="Chemin vers la vidéo à analyser")
    parser.add_argument("--output", "-o", help="Dossier de sortie pour les shorts", default="output")
    parser.add_argument("--num-shorts", "-n", type=int, help="Nombre de shorts à générer", default=3)
    parser.add_argument("--min-duration", type=int, help="Durée minimale des shorts (secondes)", default=10)
    parser.add_argument("--max-duration", type=int, help="Durée maximale des shorts (secondes)", default=60)
    parser.add_argument("--whisper-model", help="Taille du modèle Whisper (tiny, base, small, medium, large)", default="base")
    parser.add_argument("--language", help="Langue de la vidéo (fr, en, etc.)", default="fr")
    parser.add_argument("--verbose", "-v", action="store_true", help="Activer les messages détaillés")
    parser.add_argument("--skip-whisper", "-s", action="store_true", help="Ignorer la transcription Whisper (utile si problèmes)")
    
    return parser.parse_args()

def validate_video(video_path):
    """Valider l'existence et le format de la vidéo"""
    if not os.path.exists(video_path):
        print(f"{Fore.RED}Erreur: Le fichier {video_path} n'existe pas{Style.RESET_ALL}")
        return False
    
    extensions = ['.mp4', '.mov', '.avi', '.webm']
    if not any(video_path.lower().endswith(ext) for ext in extensions):
        print(f"{Fore.RED}Erreur: Le fichier doit être au format {', '.join(extensions)}{Style.RESET_ALL}")
        return False
    
    return True

def create_output_dir(output_dir):
    """Créer le répertoire de sortie s'il n'existe pas"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp")
    Path(temp_dir).mkdir(exist_ok=True)
    return output_dir, temp_dir

def print_shorts_info(shorts, output_dir):
    """Affiche des informations sur les shorts générés"""
    if not shorts:
        print(f"{Fore.YELLOW}Aucun short n'a été généré.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.GREEN}Shorts générés avec succès:{Style.RESET_ALL}")
    for i, (clip_path, start_time, end_time, score) in enumerate(shorts, 1):
        filename = os.path.basename(clip_path)
        duration = end_time - start_time
        
        # Calculer le chemin relatif ou absolu selon le besoin
        if os.path.isabs(clip_path):
            display_path = clip_path
        else:
            display_path = os.path.join(os.getcwd(), clip_path)
        
        print(f"  {i}. {Fore.CYAN}{filename}{Style.RESET_ALL}")
        print(f"     - Position: {start_time:.1f}s - {end_time:.1f}s (durée: {duration:.1f}s)")
        print(f"     - Score: {score:.2f}")
        print(f"     - Chemin: {display_path}")

def main():
    """Fonction principale"""
    # Analyser les arguments
    args = parse_arguments()
    
    # Configurer le niveau de logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Valider la vidéo
    if not validate_video(args.video_path):
        return 1
    
    # Utiliser le chemin absolu pour éviter les problèmes de relativité
    video_path = os.path.abspath(args.video_path)
    
    # Créer les répertoires de sortie
    output_dir, temp_dir = create_output_dir(args.output)
    
    # Afficher les informations du traitement
    video_name = os.path.basename(video_path)
    print(f"\n{Fore.BLUE}=== DShorts - Prototype Amélioré ==={Style.RESET_ALL}")
    print(f"Traitement de : {Fore.CYAN}{video_name}{Style.RESET_ALL}")
    print(f"Nombre de shorts demandés : {Fore.CYAN}{args.num_shorts}{Style.RESET_ALL}")
    print(f"Durée : {Fore.CYAN}{args.min_duration}s à {args.max_duration}s{Style.RESET_ALL}")
    print(f"Langue : {Fore.CYAN}{args.language}{Style.RESET_ALL}")
    
    if args.skip_whisper:
        print(f"Mode : {Fore.YELLOW}Transcription Whisper désactivée{Style.RESET_ALL}")
    else:
        print(f"Modèle Whisper : {Fore.CYAN}{args.whisper_model}{Style.RESET_ALL}")
    
    print(f"Dossier de sortie : {Fore.CYAN}{output_dir}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}==============================={Style.RESET_ALL}")
    
    # Temps de départ
    start_time = time.time()
    
    try:
        # 1. Analyser la video
        print(f"\n{Fore.GREEN}1. Analyse de la vidéo{Style.RESET_ALL}")
        video_analyzer = VideoAnalyzer(video_path)
        print(f"{Fore.CYAN}Détection des changements de scène...{Style.RESET_ALL}")
        scene_cuts = video_analyzer.detect_scenes()
        print(f"Détecté {len(scene_cuts)} changements de scène")
        
        # 2. Analyser l'audio
        print(f"\n{Fore.GREEN}2. Analyse de l'audio{Style.RESET_ALL}")
        audio_analyzer = AudioAnalyzer(video_path, temp_dir)
        print(f"{Fore.CYAN}Extraction et analyse audio...{Style.RESET_ALL}")
        audio_analyzer.load_audio()
        audio_analyzer.analyze_energy()
        silences = audio_analyzer.detect_silences()
        print(f"Détecté {len(silences)} silences significatifs")
        
        # 3. Transcription et analyse du texte (optionnel)
        text_analyzer = None
        if not args.skip_whisper:
            print(f"\n{Fore.GREEN}3. Transcription et analyse du texte{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Chargement du modèle Whisper '{args.whisper_model}'...{Style.RESET_ALL}")
            text_analyzer = TextAnalyzer(
                video_path, 
                model_size=args.whisper_model, 
                language=args.language, 
                temp_dir=temp_dir
            )
            print(f"{Fore.CYAN}Transcription de la vidéo (cela peut prendre un moment)...{Style.RESET_ALL}")
            transcript = text_analyzer.transcribe()
            
            if transcript and text_analyzer.segments:
                print(f"Transcription terminée avec {len(text_analyzer.segments)} segments")
            else:
                print(f"{Fore.YELLOW}Attention: La transcription a échoué. Continuera sans analyse de texte.{Style.RESET_ALL}")
        else:
            # Créer un analyseur de texte minimal qui renvoie toujours un score neutre
            print(f"\n{Fore.YELLOW}Transcription Whisper ignorée (--skip-whisper){Style.RESET_ALL}")
            
            class DummyTextAnalyzer:
                def get_text_score(self, start_time, end_time):
                    return 0.5
                def cleanup(self):
                    pass
            
            text_analyzer = DummyTextAnalyzer()
        
        # 4. Générer les clips avec l'algorithme amélioré
        print(f"\n{Fore.GREEN}4. Génération des shorts{Style.RESET_ALL}")
        clip_generator = ClipGenerator(
            video_path=video_path,
            output_dir=output_dir,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            overlap_threshold=0.3  # Éviter les chevauchements significatifs
        )
        
        print(f"{Fore.CYAN}Génération de {args.num_shorts} courts extraits...{Style.RESET_ALL}")
        generated_shorts = clip_generator.generate_shorts(
            video_analyzer,
            audio_analyzer,
            text_analyzer,
            num_shorts=args.num_shorts
        )
        
        # 5. Nettoyage
        print(f"\n{Fore.GREEN}5. Finalisation{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Nettoyage des fichiers temporaires...{Style.RESET_ALL}")
        audio_analyzer.cleanup()
        text_analyzer.cleanup()
        
        # 6. Résumé
        elapsed_time = time.time() - start_time
        print(f"\n{Fore.BLUE}=== Résultats ==={Style.RESET_ALL}")
        print(f"Traitement terminé en {Fore.CYAN}{elapsed_time:.2f} secondes{Style.RESET_ALL}")
        
        # Afficher les informations des shorts générés
        print_shorts_info(generated_shorts, output_dir)
        
        print(f"\n{Fore.GREEN}Ouvrez les fichiers générés pour visualiser les résultats!{Style.RESET_ALL}")
        print(f"Dossier de sortie: {os.path.abspath(output_dir)}")
        
    except Exception as e:
        print(f"\n{Fore.RED}Erreur: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())