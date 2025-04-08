"""
Module d'analyse audio pour DShorts
----------------------------------
Analyse la piste audio pour détecter les variations d'énergie, 
les silences et les moments forts qui pourraient indiquer des 
passages intéressants.
"""
import os
import numpy as np
import librosa
import logging
from moviepy.editor import VideoFileClip

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    """
    Classe responsable de l'analyse de la piste audio.
    Détecte les variations d'énergie, les silences et les moments forts.
    """
    
    def __init__(self, video_path, temp_dir=None):
        """
        Initialiser l'analyseur audio avec le chemin du fichier vidéo
        
        Args:
            video_path (str): Chemin vers le fichier vidéo
            temp_dir (str, optional): Répertoire temporaire pour l'extraction audio
        """
        self.video_path = video_path
        self.temp_dir = temp_dir or os.path.dirname(video_path)
        self.audio_path = None
        self.y = None  # Signal audio
        self.sr = None  # Taux d'échantillonnage
        self.energy = None  # Énergie audio (RMS)
        self.silence_mask = None  # Masque des silences
        
    def extract_audio(self):
        """
        Extraire la piste audio de la vidéo
        
        Returns:
            str: Chemin vers le fichier audio extrait
        """
        try:
            # Créer un chemin pour le fichier audio temporaire
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            self.audio_path = os.path.join(self.temp_dir, f"{base_name}_audio.wav")
            
            # Extraire l'audio avec MoviePy
            with VideoFileClip(self.video_path) as video:
                audio = video.audio
                audio.write_audiofile(self.audio_path, verbose=False, logger=None)
            
            logger.info(f"Audio extrait avec succès: {self.audio_path}")
            return self.audio_path
            
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction audio: {str(e)}")
            return None
    
    def load_audio(self):
        """
        Charger l'audio dans librosa pour analyse
        
        Returns:
            tuple: Signal audio et taux d'échantillonnage
        """
        try:
            if not self.audio_path:
                self.extract_audio()
                
            if not os.path.exists(self.audio_path):
                raise FileNotFoundError(f"Fichier audio non trouvé: {self.audio_path}")
                
            # Charger l'audio avec librosa
            self.y, self.sr = librosa.load(self.audio_path, sr=None)
            logger.info(f"Audio chargé avec succès: {self.audio_path}, sr={self.sr}")
            return self.y, self.sr
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement audio: {str(e)}")
            return None, None
    
    def analyze_energy(self, frame_length=1024, hop_length=512):
        """
        Analyser l'énergie audio (RMS) pour détecter les moments forts
        
        Args:
            frame_length (int): Taille de la fenêtre d'analyse
            hop_length (int): Pas d'avancement entre les fenêtres
            
        Returns:
            np.ndarray: Valeurs d'énergie RMS
        """
        try:
            if self.y is None:
                self.load_audio()
                
            # Calculer l'énergie RMS
            self.energy = librosa.feature.rms(y=self.y, frame_length=frame_length, hop_length=hop_length)[0]
            
            logger.info(f"Analyse d'énergie terminée: {len(self.energy)} frames")
            return self.energy
            
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse d'énergie: {str(e)}")
            return np.array([])
    
    def detect_silences(self, threshold_db=-40, min_silence_duration=0.5):
        """
        Détecter les silences dans l'audio
        
        Args:
            threshold_db (float): Seuil en dB pour considérer un son comme silence
            min_silence_duration (float): Durée minimale (en secondes) pour considérer un silence
            
        Returns:
            list: Liste des intervalles de silence [(start, end), ...]
        """
        try:
            if self.y is None:
                self.load_audio()
                
            # Convertir le seuil en dB en amplitude
            threshold_amp = librosa.db_to_amplitude(threshold_db)
            
            # Créer un masque des silences
            self.silence_mask = (np.abs(self.y) < threshold_amp)
            
            # Trouver les transitions (début et fin des silences)
            silence_starts = np.where(np.logical_and(~self.silence_mask[:-1], self.silence_mask[1:]))[0]
            silence_ends = np.where(np.logical_and(self.silence_mask[:-1], ~self.silence_mask[1:]))[0]
            
            # Ajuster si nécessaire
            if len(silence_starts) > len(silence_ends):
                silence_ends = np.append(silence_ends, len(self.y) - 1)
            elif len(silence_ends) > len(silence_starts):
                silence_starts = np.insert(silence_starts, 0, 0)
            
            # Convertir en secondes
            silences = [(start / self.sr, end / self.sr) for start, end in zip(silence_starts, silence_ends)
                       if (end - start) / self.sr >= min_silence_duration]
            
            logger.info(f"Détection de silences terminée: {len(silences)} silences détectés")
            return silences
            
        except Exception as e:
            logger.error(f"Erreur lors de la détection des silences: {str(e)}")
            return []
    
    def get_energy_score(self, start_time, end_time, frame_length=1024, hop_length=512):
        """
        Calcule un score basé sur l'énergie audio d'un segment
        
        Args:
            start_time (float): Début du segment en secondes
            end_time (float): Fin du segment en secondes
            frame_length (int): Taille de la fenêtre d'analyse
            hop_length (int): Pas d'avancement entre les fenêtres
            
        Returns:
            float: Score entre 0 et 1
        """
        try:
            if self.energy is None:
                self.analyze_energy(frame_length, hop_length)
                
            # Convertir les temps en indices de frames
            start_frame = int(start_time * self.sr / hop_length)
            end_frame = int(end_time * self.sr / hop_length)
            
            # Limiter aux indices valides
            start_frame = max(0, min(start_frame, len(self.energy) - 1))
            end_frame = max(0, min(end_frame, len(self.energy) - 1))
            
            if start_frame >= end_frame:
                return 0.5  # Score neutre si segment invalide
            
            # Extraire l'énergie du segment
            segment_energy = self.energy[start_frame:end_frame]
            
            if len(segment_energy) == 0:
                return 0.5
            
            # Calculer la moyenne et max de l'énergie
            mean_energy = np.mean(segment_energy)
            max_energy = np.max(segment_energy)
            
            # Normalisation par rapport à l'ensemble de l'audio
            global_max = np.max(self.energy)
            mean_score = mean_energy / global_max if global_max > 0 else 0.5
            max_score = max_energy / global_max if global_max > 0 else 0.5
            
            # Combinaison des scores (moyenne et max)
            combined_score = 0.4 * mean_score + 0.6 * max_score
            
            return combined_score
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du score d'énergie: {str(e)}")
            return 0.5  # Score neutre en cas d'erreur
    
    def get_silence_score(self, start_time, end_time):
        """
        Calcule un score basé sur la proximité du segment avec un silence
        (souvent un silence indique une transition importante)
        
        Args:
            start_time (float): Début du segment en secondes
            end_time (float): Fin du segment en secondes
            
        Returns:
            float: Score entre 0 et 1
        """
        try:
            silences = self.detect_silences()
            
            if not silences:
                return 0.5  # Score neutre si pas de silences détectés
            
            # Si le segment commence juste après un silence ou finit juste avant
            # c'est souvent un bon indicateur d'un moment important
            for silence_start, silence_end in silences:
                # Segment commence juste après un silence
                if abs(start_time - silence_end) < 1.0:
                    return 1.0
                
                # Segment finit juste avant un silence
                if abs(end_time - silence_start) < 1.0:
                    return 0.8
            
            # Calculer la distance au silence le plus proche
            min_distance = min(
                [min(abs(start_time - s_end), abs(end_time - s_start)) 
                 for s_start, s_end in silences]
            )
            
            # Score inversement proportionnel à la distance
            max_distance = 5.0  # 5 secondes comme distance maximale significative
            score = max(0, 1.0 - (min_distance / max_distance))
            
            return score
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du score de silence: {str(e)}")
            return 0.5  # Score neutre en cas d'erreur
    
    def cleanup(self):
        """Nettoyer les fichiers temporaires"""
        try:
            if self.audio_path and os.path.exists(self.audio_path):
                os.remove(self.audio_path)
                logger.info(f"Fichier audio temporaire supprimé: {self.audio_path}")
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage des fichiers temporaires: {str(e)}")