"""
Module de génération de clips pour DShorts
----------------------------------------
Génère des clips courts à partir de la vidéo d'origine
en utilisant les scores des analyseurs pour identifier les meilleurs segments.
"""
import os
import uuid
import logging
import numpy as np
from pathlib import Path
from tqdm import tqdm
from moviepy.editor import VideoFileClip

logger = logging.getLogger(__name__)

class ClipGenerator:
    """
    Classe responsable de générer les clips courts à partir de la vidéo d'origine.
    Utilise les scores des analyseurs (vidéo, audio, texte) pour identifier les meilleurs segments.
    """
    
    def __init__(self, video_path, output_dir, min_duration=10, max_duration=60, overlap_threshold=0.3):
        """
        Initialiser le générateur de clips
        
        Args:
            video_path (str): Chemin vers la vidéo originale
            output_dir (str): Répertoire de sortie pour les clips générés
            min_duration (int): Durée minimale d'un clip en secondes
            max_duration (int): Durée maximale d'un clip en secondes
            overlap_threshold (float): Seuil de chevauchement maximum entre deux clips
        """
        self.video_path = video_path
        self.output_dir = output_dir
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.overlap_threshold = overlap_threshold
        self.video_duration = None
        self.candidate_segments = []
        
        # S'assurer que le répertoire de sortie existe
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
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
    
    def generate_candidate_segments(self, step_size=3, window_sizes=None):
        """
        Générer des segments candidats de différentes tailles
        
        Args:
            step_size (int): Pas entre les débuts de segments en secondes
            window_sizes (list): Liste des tailles de fenêtre à utiliser en secondes
                               Si None, utilise [15, 20, 30, 45, 60]
        
        Returns:
            list: Liste des segments candidats [(start, end), ...]
        """
        duration = self.get_video_duration()
        if duration <= 0:
            return []
            
        # Utilisez une gamme plus variée de tailles de fenêtres
        window_sizes = window_sizes or [15, 20, 30, 45, 60]
        segments = []
        
        # Calculer le nombre approximatif de segments requis pour couvrir toute la vidéo
        target_segments = int(duration / min(window_sizes)) * 3  # Facteur 3 pour garantir suffisamment de diversité
        
        # Ajuster le pas pour obtenir un nombre raisonnable de segments
        if target_segments > 1000:
            # Limiter à 1000 segments pour des raisons de performance
            step_size = max(step_size, int(duration / (1000 / len(window_sizes))))
        
        print(f"Génération de segments avec pas de {step_size}s et fenêtres {window_sizes}s")
        
        for window_size in window_sizes:
            if window_size > duration:
                continue
                
            # Générer des segments espacés régulièrement, mais pas trop nombreux
            for start in range(0, int(duration - window_size) + 1, step_size):
                end = start + window_size
                if end <= duration:
                    segments.append((start, end))
        
        self.candidate_segments = segments
        return segments
    
    def score_segment(self, start, end, video_score, audio_score, text_score):
        """
        Calcule un score combiné pour un segment en utilisant les différents analyseurs
        
        Args:
            start (float): Temps de début du segment en secondes
            end (float): Temps de fin du segment en secondes
            video_score (float): Score d'analyse vidéo (0-1)
            audio_score (float): Score d'analyse audio (0-1)
            text_score (float): Score d'analyse texte (0-1)
            
        Returns:
            float: Score combiné (0-1)
        """
        # Poids des différentes analyses
        # Donnons plus de poids à l'audio pour privilégier les moments énergiques
        video_weight = 0.30  # Augmenté pour les changements de scène
        audio_weight = 0.40  # Priorité aux variations d'énergie audio
        text_weight = 0.30   # Si whisper échoue, moins dépendant du texte
        
        # Score combiné
        combined_score = (
            video_score * video_weight +
            audio_score * audio_weight +
            text_score * text_weight
        )
        
        # Pénalité pour les segments trop courts
        duration = end - start
        if duration < self.min_duration:
            return 0.0
            
        # Bonus/malus selon la durée optimale (15-30s est idéal pour les réseaux sociaux)
        duration_score = 1.0
        
        # Privilégier fortement les segments de 15-30s (idéal pour TikTok, Reels, etc.)
        if 15 <= duration <= 30:
            duration_score = 1.2  # Bonus pour la durée optimale
        elif 10 <= duration < 15:
            duration_score = 0.9  # Léger malus pour les clips courts
        elif 30 < duration <= 45:
            duration_score = 0.9  # Léger malus pour les clips plus longs
        elif duration > 45:
            duration_score = 0.7  # Malus plus important pour les très longs clips
            
        # Ajuster le score final
        final_score = combined_score * duration_score
        
        return min(1.0, final_score)  # Limiter à 1.0
    
    def filter_overlapping_segments(self, scored_segments, min_separation=15):
        """
        Filtrer les segments qui se chevauchent trop en gardant les meilleurs scores
        et en assurant une bonne distribution temporelle
        
        Args:
            scored_segments (list): Liste de tuples (start, end, score) triés par score décroissant
            min_separation (int): Séparation minimale en secondes entre les midpoints de deux segments
            
        Returns:
            list: Liste filtrée des meilleurs segments sans chevauchement excessif
        """
        if not scored_segments:
            return []
            
        video_duration = self.get_video_duration()
            
        # Trier les segments par score décroissant
        sorted_segments = sorted(scored_segments, key=lambda x: x[2], reverse=True)
        
        # Initialiser la liste des segments sélectionnés
        selected = []
        
        # Pour stocker les "empreintes temporelles" des segments déjà sélectionnés
        # Créer un tableau temporel pour toute la durée de la vidéo
        temporal_footprint = np.zeros(int(video_duration) + 1)
        
        # Garder les top 20% des segments candidats pour une première sélection
        top_candidates = sorted_segments[:int(len(sorted_segments) * 0.2)]
        
        # Première passe: prendre le meilleur segment dans chaque tranche temporelle
        # Diviser la vidéo en N tranches temporelles (où N est le nombre de shorts demandé)
        
        for start, end, score in top_candidates:
            # Calculer le point médian du segment
            midpoint = (start + end) / 2
            
            # Vérifier la distance avec les segments déjà sélectionnés
            too_close = False
            
            # Vérifier si ce segment chevauche trop les segments déjà sélectionnés
            for sel_start, sel_end, _ in selected:
                # Calculer le point médian du segment sélectionné
                sel_midpoint = (sel_start + sel_end) / 2
                
                # Si les points médians sont trop proches
                if abs(midpoint - sel_midpoint) < min_separation:
                    too_close = True
                    break
                
                # Calculer le chevauchement direct
                overlap_start = max(start, sel_start)
                overlap_end = min(end, sel_end)
                
                # S'il y a un chevauchement
                if overlap_start < overlap_end:
                    overlap_duration = overlap_end - overlap_start
                    segment_duration = end - start
                    
                    overlap_ratio = overlap_duration / segment_duration
                    
                    if overlap_ratio > self.overlap_threshold:
                        too_close = True
                        break
            
            # Vérifier l'empreinte temporelle
            segment_range = range(int(start), int(end)+1)
            footprint_overlap = np.sum(temporal_footprint[segment_range]) / len(segment_range)
            
            # Si ce segment est bien distinct des segments existants
            if not too_close and footprint_overlap < 0.3:
                selected.append((start, end, score))
                
                # Mettre à jour l'empreinte temporelle
                temporal_footprint[segment_range] += 1
        
        # Seconde passe: compléter avec les meilleurs segments restants si nécessaire
        if len(selected) < 3:  # Si on n'a pas assez de segments
            # Trier le reste des segments par score
            remaining = [s for s in sorted_segments if s not in selected]
            
            for start, end, score in remaining:
                # Calculer le point médian du segment
                midpoint = (start + end) / 2
                
                # Vérifier la distance avec les segments déjà sélectionnés
                too_close = False
                
                for sel_start, sel_end, _ in selected:
                    sel_midpoint = (sel_start + sel_end) / 2
                    
                    # Distance minimale entre les points médians
                    if abs(midpoint - sel_midpoint) < min_separation/2:  # Relâché pour la seconde passe
                        too_close = True
                        break
                
                # Si ce segment est suffisamment distinct
                if not too_close:
                    selected.append((start, end, score))
                    
                    # Limiter le nombre total de segments
                    if len(selected) >= 10:
                        break
        
        # Trier les segments sélectionnés par position temporelle pour une présentation logique
        selected.sort(key=lambda x: x[0])
        
        return selected
    
    def extract_clip(self, start_time, end_time, output_path=None):
        """
        Extraire un clip de la vidéo originale
        
        Args:
            start_time (float): Temps de début en secondes
            end_time (float): Temps de fin en secondes
            output_path (str, optional): Chemin de sortie spécifique
            
        Returns:
            str: Chemin du clip généré ou None en cas d'erreur
        """
        try:
            # Générer un nom de fichier unique si non spécifié
            if output_path is None:
                filename = f"short_{uuid.uuid4().hex[:8]}_{int(start_time)}_{int(end_time)}.mp4"
                output_path = os.path.join(self.output_dir, filename)
            
            print(f"Extraction du clip {os.path.basename(output_path)}...")
            
            # Extraire le clip
            with VideoFileClip(self.video_path) as video:
                # Ajuster les temps de début et fin pour rester dans les limites de la vidéo
                start_time = max(0, start_time)
                end_time = min(video.duration, end_time)
                
                if end_time <= start_time:
                    raise ValueError("Temps de fin inférieur ou égal au temps de début")
                
                # Créer le sous-clip et sauvegarder
                subclip = video.subclip(start_time, end_time)
                subclip.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile=f"{output_path}.temp-audio.m4a",
                    remove_temp=True,
                    preset='medium',  # équilibre entre qualité et vitesse
                    threads=2,
                    verbose=False,
                    logger=None
                )
            
            logger.info(f"Clip extrait avec succès: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du clip: {str(e)}")
            return None
    
    def generate_shorts(self, video_analyzer, audio_analyzer, text_analyzer, num_shorts=5):
        """
        Générer les clips courts en utilisant les analyses vidéo, audio et texte
        
        Args:
            video_analyzer: Instance de VideoAnalyzer
            audio_analyzer: Instance de AudioAnalyzer
            text_analyzer: Instance de TextAnalyzer
            num_shorts (int): Nombre de shorts à générer
            
        Returns:
            list: Liste des chemins vers les clips générés avec leurs scores
                 [(path, start_time, end_time, score), ...]
        """
        results = []
        
        try:
            # Obtenir la durée totale de la vidéo
            video_duration = self.get_video_duration()
            print(f"Durée totale de la vidéo: {video_duration:.1f}s")
            
            # Si la vidéo est très courte, ajuster la durée minimale des segments
            if video_duration < 60:
                self.min_duration = min(5, video_duration / 3)
            
            # Générer des segments candidats
            if not self.candidate_segments:
                print("Génération des segments candidats...")
                self.generate_candidate_segments()
            
            if not self.candidate_segments:
                logger.error("Aucun segment candidat généré")
                return []
            
            print(f"Analyse de {len(self.candidate_segments)} segments candidats...")
            
            # Diviser la vidéo en régions pour favoriser la diversité
            video_regions = []
            region_size = video_duration / 5  # Diviser la vidéo en 5 régions
            for i in range(5):
                start = i * region_size
                end = (i + 1) * region_size
                if end > video_duration:
                    end = video_duration
                video_regions.append((start, end))
            
            # Évaluer chaque segment candidat
            scored_segments = []
            for start, end in tqdm(self.candidate_segments, desc="Évaluation des segments"):
                # Obtenir les scores des différents analyseurs
                video_score = video_analyzer.get_scene_score(start, end)
                audio_score = audio_analyzer.get_energy_score(start, end)
                text_score = text_analyzer.get_text_score(start, end)
                
                # Identifier à quelle région appartient ce segment
                region_idx = None
                midpoint = (start + end) / 2
                for i, (region_start, region_end) in enumerate(video_regions):
                    if region_start <= midpoint < region_end:
                        region_idx = i
                        break
                
                # Combiner les scores
                combined_score = self.score_segment(start, end, video_score, audio_score, text_score)
                
                if combined_score > 0:
                    scored_segments.append((start, end, combined_score, region_idx))
            
            print(f"Segments candidats évalués: {len(scored_segments)} segments valides")
            
            # Assurer une distribution plus uniforme entre les régions
            # Pour chaque région, prendre au moins un segment (s'il existe) des X segments les mieux notés
            region_selections = []
            for region_idx in range(len(video_regions)):
                # Filtrer les segments pour cette région
                region_segments = [(s, e, score) for s, e, score, r_idx in scored_segments if r_idx == region_idx]
                # Trier par score
                region_segments.sort(key=lambda x: x[2], reverse=True)
                # Prendre le meilleur segment s'il existe
                if region_segments:
                    region_selections.append(region_segments[0])
            
            # Si on n'a pas assez de segments, prendre les meilleurs parmi tous les segments
            all_segments = [(s, e, score) for s, e, score, _ in scored_segments]
            
            # Combiner la sélection régionale avec les meilleurs segments globaux
            combined_selections = region_selections.copy()
            
            # Trier tous les segments par score
            all_segments.sort(key=lambda x: x[2], reverse=True)
            
            # Ajouter les meilleurs segments globaux, en évitant les duplications
            for segment in all_segments:
                if segment not in combined_selections:
                    combined_selections.append(segment)
                    if len(combined_selections) >= num_shorts * 2:  # Prendre 2x plus pour le filtrage
                        break
            
            # Filtrer les segments qui se chevauchent trop
            print("Filtrage des segments qui se chevauchent...")
            min_separation = max(15, video_duration / (num_shorts * 2))  # Assurer une bonne séparation
            filtered_segments = self.filter_overlapping_segments(combined_selections, min_separation)
            
            # Limiter au nombre demandé
            top_segments = filtered_segments[:num_shorts]
            
            print(f"Extraction des {len(top_segments)} meilleurs segments...")
            
            # Extraire les clips
            for i, (start, end, score) in enumerate(top_segments):
                # Arrondir les temps de début/fin pour une meilleure expérience
                start_rounded = max(0, int(start))
                end_rounded = int(end)
                
                # Nommage standardisé
                filename = f"short_{i+1}_score_{int(score*100)}_time_{start_rounded}_{end_rounded}.mp4"
                output_path = os.path.join(self.output_dir, filename)
                
                # Extraire le clip
                clip_path = self.extract_clip(start_rounded, end_rounded, output_path)
                
                if clip_path:
                    results.append((clip_path, start_rounded, end_rounded, score))
            
            logger.info(f"Génération terminée: {len(results)} shorts créés")
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération des shorts: {str(e)}")
            return results