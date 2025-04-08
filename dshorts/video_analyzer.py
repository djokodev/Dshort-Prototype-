"""
Module d'analyse vidéo pour DShorts
-----------------------------------
Détecte les changements de scène et autres points d'intérêt visuels
pour identifier les meilleurs moments à extraire.
"""
import os
import logging
import numpy as np
from scenedetect import ContentDetector, SceneManager, open_video
from moviepy.editor import VideoFileClip

logger = logging.getLogger(__name__)

class VideoAnalyzer:
    """
    Classe responsable de l'analyse de la piste vidéo.
    Utilisée pour détecter les changements de scène et autres points d'intérêt visuels.
    """
    
    def __init__(self, video_path):
        """
        Initialiser l'analyseur vidéo avec le chemin du fichier vidéo
        
        Args:
            video_path (str): Chemin vers le fichier vidéo
        """
        self.video_path = video_path
        self.scenes = []
        self.cut_list = []
        self.video_duration = None
        
    def get_video_duration(self):
        """
        Obtenir la durée totale de la vidéo
        
        Returns:
            float: Durée en secondes
        """
        if self.video_duration is not None:
            return self.video_duration
            
        try:
            with VideoFileClip(self.video_path) as clip:
                self.video_duration = clip.duration
            return self.video_duration
        except Exception as e:
            logger.error(f"Erreur lors de l'obtention de la durée de la vidéo: {str(e)}")
            return 0
        
    def detect_scenes(self, threshold=27.0):
        """
        Détecter les changements de scène dans la vidéo
        
        Args:
            threshold (float): Seuil de détection des scènes (27.0 par défaut)
            
        Returns:
            list: Liste des changements de scène détectés (en secondes)
        """
        try:
            # Ouvrir la vidéo avec PySceneDetect
            video = open_video(self.video_path)
            
            # Créer le gestionnaire de scènes
            scene_manager = SceneManager()
            
            # Ajouter le détecteur de contenu
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            
            # Détecter les scènes
            scene_manager.detect_scenes(video)
            
            # Récupérer la liste des scènes détectées
            self.scenes = scene_manager.get_scene_list()
            
            # Convertir en liste de secondes (timecodes des coupures)
            self.cut_list = [scene[0].get_seconds() for scene in self.scenes]
            
            logger.info(f"Détection de scènes terminée: {len(self.cut_list)} changements détectés")
            return self.cut_list
            
        except Exception as e:
            logger.error(f"Erreur lors de la détection des scènes: {str(e)}")
            return []
    
    def get_scene_score(self, start_time, end_time):
        """
        Calcule un score pour un segment vidéo en fonction de sa proximité 
        avec un changement de scène
        
        Args:
            start_time (float): Début du segment en secondes
            end_time (float): Fin du segment en secondes
            
        Returns:
            float: Score entre 0 et 1
        """
        if not self.cut_list:
            return 0.5  # Si pas de détection de scène, score neutre
        
        # Vérifier si le segment contient un changement de scène
        for cut in self.cut_list:
            if start_time <= cut <= end_time:
                return 1.0  # Score maximal si changement de scène dans le segment
        
        # Sinon, calculer la proximité avec le changement de scène le plus proche
        closest_cut = min(self.cut_list, key=lambda x: min(abs(x - start_time), abs(x - end_time)))
        closest_distance = min(abs(closest_cut - start_time), abs(closest_cut - end_time))
        
        # Calculer un score inversement proportionnel à la distance (plus c'est proche, meilleur est le score)
        max_distance = 10.0  # Considérer 10 secondes comme distance maximale significative
        score = max(0, 1.0 - (closest_distance / max_distance))
        
        return score