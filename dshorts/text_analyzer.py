"""
Module d'analyse de texte pour DShorts
-------------------------------------
Utilise Whisper pour la transcription et l'analyse sémantique
du contenu verbal de la vidéo.
"""
import os
import re
import json
import logging
import whisper
import numpy as np
from pathlib import Path
from moviepy.editor import VideoFileClip

logger = logging.getLogger(__name__)

class TextAnalyzer:
    """
    Classe responsable de la transcription et de l'analyse du contenu parlé.
    Utilise Whisper pour la transcription et l'analyse sémantique.
    """
    
    # Mots clés (en français) qui pourraient indiquer des moments importants
    HIGHLIGHT_KEYWORDS = [
        "important", "essentiel", "crucial", "clé", "fondamental", 
        "attention", "notez", "remarquez", "n'oubliez pas", "rappelez-vous",
        "premièrement", "deuxièmement", "troisièmement", "enfin", "conclusion",
        "en résumé", "pour conclure", "donc", "ainsi", "par conséquent",
        "exemple", "illustration", "cas", "preuve", "démonstration",
        "conseil", "astuce", "recommandation", "suggestion", "idée",
        "problème", "solution", "challenge", "défi", "opportunité",
        "question", "réponse", "pourquoi", "comment", "quand", "où", "qui"
    ]
    
    # Expressions régulières pour détecter des questions
    QUESTION_PATTERNS = [
        r'\?',  # Point d'interrogation
        r'^(est-ce que|qu\'est-ce que|comment|pourquoi|quand|où|qui|quel|quelle|quels|quelles)',  # Début de question
        r'(est-ce que|qu\'est-ce que|comment|pourquoi|quand|où|qui|quel|quelle|quels|quelles).*\?'  # Question complète
    ]
    
    def __init__(self, video_path, model_size="base", language="fr", temp_dir=None):
        """
        Initialise l'analyseur de texte
        
        Args:
            video_path (str): Chemin vers le fichier vidéo
            model_size (str): Taille du modèle Whisper ("tiny", "base", "small", "medium", "large")
            language (str): Code langue pour la transcription (par défaut: "fr" pour français)
            temp_dir (str, optional): Répertoire pour les fichiers temporaires
        """
        self.video_path = os.path.abspath(video_path)  # Utiliser le chemin absolu
        self.model_size = model_size
        self.language = language
        self.temp_dir = temp_dir or os.path.dirname(video_path)
        
        # S'assurer que le répertoire temporaire existe
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.transcript = None
        self.segments = None
        self.transcript_path = None
        self.transcription_failed = False
        self.audio_path = None
    
    def load_model(self):
        """
        Charge le modèle Whisper
        
        Returns:
            bool: True si le chargement a réussi, False sinon
        """
        try:
            self.model = whisper.load_model(self.model_size)
            logger.info(f"Modèle Whisper '{self.model_size}' chargé avec succès")
            return True
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle Whisper: {str(e)}")
            return False
    
    def extract_audio(self):
        """
        Extrait l'audio de la vidéo pour la transcription
        
        Returns:
            str: Chemin du fichier audio extrait ou None en cas d'erreur
        """
        try:
            # Créer un chemin pour le fichier audio temporaire
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            self.audio_path = os.path.join(self.temp_dir, f"{base_name}_audio.wav")
            
            # Vérifier si la vidéo existe
            if not os.path.exists(self.video_path):
                raise FileNotFoundError(f"Vidéo non trouvée: {self.video_path}")
            
            # Extraire l'audio avec MoviePy
            print(f"Extraction de l'audio à partir de {self.video_path}")
            with VideoFileClip(self.video_path) as video:
                if video.audio is None:
                    logger.warning("La vidéo ne contient pas d'audio")
                    return None
                
                video.audio.write_audiofile(self.audio_path, verbose=False, logger=None)
            
            logger.info(f"Audio extrait avec succès: {self.audio_path}")
            return self.audio_path
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction audio: {str(e)}")
            return None
    
    def transcribe(self, force=False):
        """
        Transcrit la vidéo en texte avec horodatage
        
        Args:
            force (bool): Forcer la retranscription même si une transcription existe déjà
            
        Returns:
            dict: Résultat de la transcription avec segments horodatés
        """
        try:
            # Si une précédente tentative a échoué et qu'on ne force pas, renvoyer None
            if self.transcription_failed and not force:
                logger.warning("Transcription précédemment échouée et non forcée")
                return None
            
            # Vérifier si une transcription existe déjà
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            self.transcript_path = os.path.join(self.temp_dir, f"{base_name}_transcript.json")
            
            if not force and os.path.exists(self.transcript_path):
                try:
                    with open(self.transcript_path, 'r', encoding='utf-8') as f:
                        self.transcript = json.load(f)
                        self.segments = self.transcript.get("segments", [])
                        logger.info(f"Transcription existante chargée depuis {self.transcript_path}")
                        return self.transcript
                except Exception as e:
                    logger.warning(f"Erreur lors du chargement de la transcription existante: {str(e)}")
                    # Continuer pour régénérer la transcription
            
            # Charger le modèle si nécessaire
            if self.model is None:
                if not self.load_model():
                    self.transcription_failed = True
                    return None
            
            # Extraire l'audio si nécessaire
            audio_source = self.audio_path or self.extract_audio() or self.video_path
            
            # Vérifier si le fichier source existe
            if not os.path.exists(audio_source):
                logger.error(f"Fichier source pour transcription non trouvé: {audio_source}")
                self.transcription_failed = True
                return None
            
            # Transcription avec affichage de progression
            logger.info(f"Début de la transcription de {audio_source}")
            print(f"Transcription en cours, cela peut prendre quelques minutes...")
            
            try:
                self.transcript = self.model.transcribe(
                    audio_source, 
                    language=self.language,
                    verbose=False
                )
                
                # Extraire les segments
                self.segments = self.transcript.get("segments", [])
                
                # Sauvegarder la transcription
                with open(self.transcript_path, 'w', encoding='utf-8') as f:
                    json.dump(self.transcript, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Transcription terminée et sauvegardée dans {self.transcript_path}")
                print(f"Transcription terminée ({len(self.segments)} segments)")
                
                self.transcription_failed = False
                return self.transcript
                
            except Exception as e:
                logger.error(f"Erreur pendant la transcription: {str(e)}")
                self.transcription_failed = True
                return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la transcription: {str(e)}")
            self.transcription_failed = True
            return None
    
    def get_segment_at_time(self, time_seconds):
        """
        Récupère le segment textuel à un moment précis
        
        Args:
            time_seconds (float): Temps en secondes
            
        Returns:
            dict: Segment contenant le texte à ce moment ou None
        """
        if self.segments is None:
            self.transcribe()
            
        if not self.segments:
            return None
            
        # Trouver le segment qui contient ce temps
        for segment in self.segments:
            start = segment.get("start", 0)
            end = segment.get("end", 0)
            
            if start <= time_seconds <= end:
                return segment
                
        return None
    
    def get_text_between(self, start_time, end_time):
        """
        Récupère le texte transcrit entre deux moments
        
        Args:
            start_time (float): Temps de début en secondes
            end_time (float): Temps de fin en secondes
            
        Returns:
            str: Texte transcrit entre les deux temps
        """
        if self.segments is None:
            self.transcribe()
            
        if not self.segments:
            return ""
            
        # Rassembler tous les segments qui se chevauchent avec l'intervalle
        relevant_segments = []
        for segment in self.segments:
            seg_start = segment.get("start", 0)
            seg_end = segment.get("end", 0)
            
            # Vérifier si le segment chevauche l'intervalle
            if (seg_start <= end_time and seg_end >= start_time):
                relevant_segments.append(segment.get("text", ""))
                
        return " ".join(relevant_segments)
    
    def contains_keyword(self, text):
        """
        Vérifie si le texte contient des mots-clés importants
        
        Args:
            text (str): Texte à analyser
            
        Returns:
            bool: True si des mots-clés sont présents, False sinon
        """
        if not text:
            return False
            
        text_lower = text.lower()
        
        for keyword in self.HIGHLIGHT_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
                
        return False
    
    def is_question(self, text):
        """
        Détecte si le texte est une question
        
        Args:
            text (str): Texte à analyser
            
        Returns:
            bool: True si le texte est une question, False sinon
        """
        if not text:
            return False
            
        text_lower = text.lower()
        
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, text_lower):
                return True
                
        return False
    
    def get_text_score(self, start_time, end_time):
        """
        Calcule un score de pertinence pour le texte entre deux moments
        
        Args:
            start_time (float): Temps de début en secondes
            end_time (float): Temps de fin en secondes
            
        Returns:
            float: Score entre 0 et 1
        """
        try:
            if self.segments is None:
                if not self.transcribe():
                    # Si la transcription échoue, attribuer un score basé uniquement sur la durée
                    duration = end_time - start_time
                    # Favoriser les segments d'environ 30 secondes
                    if 25 <= duration <= 35:
                        return 0.6
                    elif 20 <= duration <= 40:
                        return 0.5
                    else:
                        return 0.4
                
            if not self.segments:
                return 0.5  # Score neutre si pas de transcription
                
            # Récupérer le texte dans l'intervalle
            text = self.get_text_between(start_time, end_time)
            
            if not text.strip():
                return 0.3  # Score faible si pas de texte
                
            score = 0.5  # Score de base
            
            # Vérifier la présence de mots-clés
            if self.contains_keyword(text):
                score += 0.3
                
            # Vérifier si c'est une question
            if self.is_question(text):
                score += 0.2
                
            # Bonus pour la longueur du texte (favoriser les segments avec contenu significatif)
            words = len(text.split())
            duration = end_time - start_time
            words_per_second = words / duration if duration > 0 else 0
            
            # Idéalement, on veut une densité de parole suffisante mais pas excessive
            if 0.5 <= words_per_second <= 3.0:
                score += 0.1
            
            return min(1.0, score)  # Limiter à 1.0
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du score textuel: {str(e)}")
            return 0.5  # Score neutre en cas d'erreur
    
    def cleanup(self):
        """Nettoyer les fichiers temporaires"""
        try:
            # Nettoyer le fichier audio temporaire
            if self.audio_path and os.path.exists(self.audio_path):
                os.remove(self.audio_path)
                logger.info(f"Fichier audio temporaire supprimé: {self.audio_path}")
                
            # Conserver la transcription pour référence future
            if self.transcript_path and os.path.exists(self.transcript_path):
                logger.info(f"Fichier de transcription conservé pour analyse: {self.transcript_path}")
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage des fichiers temporaires: {str(e)}")