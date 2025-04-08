"""
DShorts - Serveur Web Simple
---------------------------
Serveur web natif Python pour le prototype DShorts.
"""

import os
import json
import cgi
import uuid
import threading
import mimetypes
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import des modules DShorts
from dshorts.video_analyzer import VideoAnalyzer
from dshorts.audio_analyzer import AudioAnalyzer
from dshorts.text_analyzer import TextAnalyzer
from dshorts.clip_generator import ClipGenerator

# Dossiers pour les fichiers
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
TEMP_FOLDER = "temp"
STATIC_FOLDER = "static"
HTML_FOLDER = "html"

# Configuration
HOST = "localhost"
PORT = 8080
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "webm"}

# Créer les dossiers nécessaires
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
Path(TEMP_FOLDER).mkdir(exist_ok=True)

# Stockage des tâches en cours (en mémoire)
tasks = {}


def allowed_file(filename):
    """Vérifie si le fichier a une extension autorisée"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def process_video(
    task_id,
    video_path,
    num_shorts=3,
    min_duration=10,
    max_duration=60,
    whisper_model="tiny",
    language="fr",
):
    """
    Fonction qui traite la vidéo et génère les shorts en arrière-plan
    """
    try:
        # Mise à jour du statut
        tasks[task_id]["status"] = "processing"
        tasks[task_id]["progress"] = 5
        tasks[task_id]["message"] = "Analyse vidéo en cours..."

        # 1. Analyse vidéo
        video_analyzer = VideoAnalyzer(video_path)
        scenes = video_analyzer.detect_scenes()
        tasks[task_id]["progress"] = 20
        tasks[task_id]["message"] = f"Détecté {len(scenes)} changements de scène"

        # 2. Analyse audio
        tasks[task_id]["message"] = "Analyse audio en cours..."
        audio_analyzer = AudioAnalyzer(video_path, TEMP_FOLDER)
        audio_analyzer.load_audio()
        audio_analyzer.analyze_energy()
        silences = audio_analyzer.detect_silences()
        tasks[task_id]["progress"] = 40
        tasks[task_id]["message"] = f"Détecté {len(silences)} silences"

        # 3. Transcription avec un modèle plus petit pour plus de rapidité
        tasks[task_id]["message"] = "Transcription en cours..."
        text_analyzer = TextAnalyzer(
            video_path,
            model_size=whisper_model,
            language=language,
            temp_dir=TEMP_FOLDER,
        )
        text_analyzer.transcribe()
        tasks[task_id]["progress"] = 70
        tasks[task_id]["message"] = "Transcription terminée"

        # 4. Génération des shorts
        output_dir = os.path.join(OUTPUT_FOLDER, task_id)
        Path(output_dir).mkdir(exist_ok=True)

        tasks[task_id]["message"] = f"Génération de {num_shorts} shorts..."
        clip_generator = ClipGenerator(
            video_path=video_path,
            output_dir=output_dir,
            min_duration=min_duration,
            max_duration=max_duration,
            overlap_threshold=0.3,
        )

        generated_shorts = clip_generator.generate_shorts(
            video_analyzer, audio_analyzer, text_analyzer, num_shorts=num_shorts
        )

        # 5. Nettoyage
        tasks[task_id]["message"] = "Finalisation..."
        audio_analyzer.cleanup()
        text_analyzer.cleanup()

        # 6. Mise à jour du résultat
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id][
            "message"
        ] = f"{len(generated_shorts)} shorts générés avec succès"
        tasks[task_id]["shorts"] = []

        for clip_path, start_time, end_time, score in generated_shorts:
            tasks[task_id]["shorts"].append(
                {
                    "filename": os.path.basename(clip_path),
                    "path": clip_path,
                    "start_time": start_time,
                    "end_time": end_time,
                    "score": score,
                    "duration": end_time - start_time,
                }
            )

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = f"Erreur: {str(e)}"
        print(f"Erreur lors du traitement: {e}")


class DshortsRequestHandler(BaseHTTPRequestHandler):

    def _send_cors_headers(self):
        """Ajoute les en-têtes CORS pour les requêtes cross-origin"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "X-Requested-With, Content-Type"
        )

    def do_OPTIONS(self):
        """Gère les requêtes OPTIONS pour CORS"""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Gère les requêtes GET"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Servir la page d'accueil
        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            with open(os.path.join(HTML_FOLDER, "index.html"), "rb") as file:
                self.wfile.write(file.read())
            return

        # Servir les fichiers statiques
        if path.startswith("/static/"):
            file_path = path[1:]  # Enlever le premier /
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(file_path)
                self.send_header(
                    "Content-type", content_type or "application/octet-stream"
                )
                self.end_headers()
                with open(file_path, "rb") as file:
                    self.wfile.write(file.read())
                return
            else:
                self.send_error(404, "File Not Found")
                return

        # Servir les shorts générés
        if path.startswith("/outputs/"):
            file_path = path[1:]  # Enlever le premier /
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(file_path)
                self.send_header(
                    "Content-type", content_type or "application/octet-stream"
                )
                # Ajouter l'en-tête pour télécharger le fichier
                if "download" in parsed_path.query:
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{os.path.basename(file_path)}"',
                    )
                self.end_headers()
                with open(file_path, "rb") as file:
                    self.wfile.write(file.read())
                return
            else:
                self.send_error(404, "File Not Found")
                return

        # API pour obtenir le statut d'une tâche
        if path.startswith("/api/task/"):
            task_id = path.split("/")[-1]
            if task_id in tasks:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(tasks[task_id]).encode())
                return
            else:
                self.send_error(404, "Task Not Found")
                return

        # Si aucune route ne correspond
        self.send_error(404, "Route Not Found")

    def do_POST(self):
        """Gère les requêtes POST"""
        if self.path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")

            # Vérifier si c'est un formulaire multipart
            if not content_type.startswith("multipart/form-data"):
                self.send_error(400, "Bad Request - Expected multipart/form-data")
                return

            # Analyser le formulaire
            form = cgi.FieldStorage(
                fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"}
            )

            # Vérifier si le fichier est présent
            if "video" not in form:
                self.send_error(400, "Bad Request - No video file provided")
                return

            # Obtenir le fichier
            fileitem = form["video"]

            # Vérifier si c'est vraiment un fichier
            if not fileitem.filename:
                self.send_error(400, "Bad Request - Empty filename")
                return

            # Vérifier l'extension
            if not allowed_file(fileitem.filename):
                self.send_error(400, "Bad Request - Invalid file extension")
                return

            # Créer un ID de tâche unique
            task_id = str(uuid.uuid4())

            # Sauvegarder le fichier
            filename = f"{task_id}_{os.path.basename(fileitem.filename)}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            with open(filepath, "wb") as f:
                f.write(fileitem.file.read())

            # Obtenir les paramètres optionnels du formulaire
            num_shorts = int(form.getvalue("num_shorts", 3))
            min_duration = int(form.getvalue("min_duration", 10))
            max_duration = int(form.getvalue("max_duration", 60))
            whisper_model = form.getvalue("whisper_model", "tiny")
            language = form.getvalue("language", "fr")

            # Créer une tâche
            tasks[task_id] = {
                "id": task_id,
                "filename": filename,
                "original_name": fileitem.filename,
                "status": "pending",
                "progress": 0,
                "message": "En attente...",
                "shorts": [],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Lancer le traitement en arrière-plan
            thread = threading.Thread(
                target=process_video,
                args=(
                    task_id,
                    filepath,
                    num_shorts,
                    min_duration,
                    max_duration,
                    whisper_model,
                    language,
                ),
            )
            thread.daemon = True
            thread.start()

            # Répondre avec l'ID de la tâche
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"task_id": task_id}).encode())
            return

        # Si aucune route ne correspond
        self.send_error(404, "Route Not Found")


def run_server():
    """Démarre le serveur HTTP"""
    server = HTTPServer((HOST, PORT), DshortsRequestHandler)
    print(f"Serveur démarré sur http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    print("Serveur arrêté")


if __name__ == "__main__":
    run_server()
