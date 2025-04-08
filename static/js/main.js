// Éléments DOM
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');
const cancelBtn = document.getElementById('cancel-btn');
const progressSection = document.getElementById('progress-section');
const uploadSection = document.getElementById('upload-section');
const resultsSection = document.getElementById('results-section');
const progressBar = document.getElementById('progress-bar');
const progressMessage = document.getElementById('progress-message');
const progressFilename = document.getElementById('progress-filename');
const resultsFilename = document.getElementById('results-filename');
const resultsMessage = document.getElementById('results-message');
const shortsContainer = document.getElementById('shorts-container');
const notification = document.getElementById('notification');
const notificationMessage = document.getElementById('notification-message');
const notificationClose = document.getElementById('notification-close');

// Options
const numShortsInput = document.getElementById('num-shorts');
const minDurationInput = document.getElementById('min-duration');
const maxDurationInput = document.getElementById('max-duration');
const whisperModelSelect = document.getElementById('whisper-model');
const languageSelect = document.getElementById('language');

// Variables d'état
let selectedFile = null;
let currentTaskId = null;
let pollingInterval = null;

// Event Listeners
document.addEventListener('DOMContentLoaded', init);

function init() {
    // Événements pour l'upload de fichier
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);
    fileInput.addEventListener('change', handleFileSelect);
    
    // Boutons
    uploadBtn.addEventListener('click', handleUpload);
    cancelBtn.addEventListener('click', cancelTask);
    notificationClose.addEventListener('click', closeNotification);
    
    // Validation des options
    numShortsInput.addEventListener('change', validateNumberInput);
    minDurationInput.addEventListener('change', validateDurationInputs);
    maxDurationInput.addEventListener('change', validateDurationInputs);
}

// Gestion du Drag & Drop
function handleDragOver(e) {
    e.preventDefault();
    dropZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    dropZone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    
    if (e.dataTransfer.files.length) {
        const file = e.dataTransfer.files[0];
        if (validateFile(file)) {
            selectedFile = file;
            updateUploadZone();
        }
    }
}

function handleFileSelect(e) {
    if (fileInput.files.length) {
        const file = fileInput.files[0];
        if (validateFile(file)) {
            selectedFile = file;
            updateUploadZone();
        }
    }
}

// Validation du fichier
function validateFile(file) {
    // Vérifier le type de fichier
    const validTypes = ['video/mp4', 'video/quicktime', 'video/avi', 'video/webm'];
    if (!validTypes.includes(file.type)) {
        showNotification('Le format de fichier n\'est pas supporté. Utilisez MP4, MOV, AVI ou WEBM.', 'error');
        return false;
    }
    
    // Vérifier la taille du fichier
    const maxSize = 500 * 1024 * 1024; // 500 MB
    if (file.size > maxSize) {
        showNotification('Le fichier est trop volumineux. La taille maximale est de 500 MB.', 'error');
        return false;
    }
    
    return true;
}

// Mettre à jour la zone d'upload avec le fichier sélectionné
function updateUploadZone() {
    if (selectedFile) {
        const fileSize = formatFileSize(selectedFile.size);
        dropZone.innerHTML = `
            <div class="upload-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <path d="M12 18v-6"></path>
                    <path d="M9 15h6"></path>
                </svg>
            </div>
            <p><strong>${selectedFile.name}</strong> (${fileSize})</p>
            <p class="upload-limits">Cliquez pour choisir un autre fichier</p>
        `;
        
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = 'Démarrer le traitement';
    } else {
        dropZone.innerHTML = `
            <div class="upload-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
            </div>
            <p>Déposez votre vidéo ici ou <span class="highlight">cliquez pour choisir un fichier</span></p>
            <p class="upload-limits">Formats acceptés : MP4, MOV, AVI, WEBM (Max 500 MB, 10 min)</p>
        `;
        
        uploadBtn.disabled = true;
    }
}

// Validation des entrées numériques
function validateNumberInput(e) {
    const input = e.target;
    let value = parseInt(input.value);
    
    if (isNaN(value) || value < parseInt(input.min)) {
        value = parseInt(input.min);
    } else if (value > parseInt(input.max)) {
        value = parseInt(input.max);
    }
    
    input.value = value;
}

function validateDurationInputs() {
    const minDuration = parseInt(minDurationInput.value);
    const maxDuration = parseInt(maxDurationInput.value);
    
    if (minDuration >= maxDuration) {
        maxDurationInput.value = minDuration + 5;
    }
}

// Gestion de l'upload et du traitement
async function handleUpload() {
    if (!selectedFile) return;
    
    // Créer un FormData
    const formData = new FormData();
    formData.append('video', selectedFile);
    formData.append('num_shorts', numShortsInput.value);
    formData.append('min_duration', minDurationInput.value);
    formData.append('max_duration', maxDurationInput.value);
    formData.append('whisper_model', whisperModelSelect.value);
    formData.append('language', languageSelect.value);
    
    try {
        // Afficher la section de progression
        uploadSection.style.display = 'none';
        progressSection.style.display = 'block';
        progressFilename.textContent = selectedFile.name;
        progressBar.style.width = '0%';
        progressMessage.textContent = 'Envoi de la vidéo...';
        
        // Envoyer la requête
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Erreur lors de l\'envoi de la vidéo');
        }
        
        const data = await response.json();
        currentTaskId = data.task_id;
        
        // Démarrer le suivi de la tâche
        startPollingTaskStatus();
        
    } catch (error) {
        showNotification(error.message, 'error');
        resetUI();
    }
}

// Suivi de l'état de la tâche
function startPollingTaskStatus() {
    if (!currentTaskId) return;
    
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/task/${currentTaskId}`);
            
            if (!response.ok) {
                clearInterval(pollingInterval);
                throw new Error('Erreur lors de la récupération de l\'état de la tâche');
            }
            
            const taskData = await response.json();
            updateTaskProgress(taskData);
            
            // Si la tâche est terminée ou a échoué, arrêter le polling
            if (taskData.status === 'completed' || taskData.status === 'failed') {
                clearInterval(pollingInterval);
                
                if (taskData.status === 'completed') {
                    showResults(taskData);
                } else {
                    showNotification(`Erreur: ${taskData.message}`, 'error');
                    resetUI();
                }
            }
            
        } catch (error) {
            clearInterval(pollingInterval);
            showNotification(error.message, 'error');
            resetUI();
        }
    }, 2000);
}

// Mise à jour de la progression
function updateTaskProgress(taskData) {
    progressBar.style.width = `${taskData.progress}%`;
    progressMessage.textContent = taskData.message || 'Traitement en cours...';
}

// Affichage des résultats
function showResults(taskData) {
    // Masquer la section de progression
    progressSection.style.display = 'none';
    
    // Afficher la section des résultats
    resultsSection.style.display = 'block';
    resultsFilename.textContent = taskData.original_name || 'Vidéo traitée';
    resultsMessage.textContent = taskData.message || 'Traitement terminé';
    
    // Vider le conteneur de shorts
    shortsContainer.innerHTML = '';
    
    // Ajouter chaque short
    if (taskData.shorts && taskData.shorts.length > 0) {
        taskData.shorts.forEach(short => {
            const shortCard = document.createElement('div');
            shortCard.className = 'short-card';
            
            const score = Math.round(short.score * 100);
            const duration = Math.round(short.duration);
            
            shortCard.innerHTML = `
                <video controls>
                    <source src="/outputs/${taskData.id}/${short.filename}" type="video/mp4">
                    Votre navigateur ne supporte pas les vidéos HTML5.
                </video>
                <div class="short-info">
                    <div class="short-title">Short #${taskData.shorts.indexOf(short) + 1}</div>
                    <div class="short-meta">
                        Score: ${score}% | Durée: ${duration}s | Position: ${short.start_time}s - ${short.end_time}s
                    </div>
                    <a href="/outputs/${taskData.id}/${short.filename}?download=true" class="btn btn-download">
                        <i class="download-icon"></i> Télécharger
                    </a>
                </div>
            `;
            
            shortsContainer.appendChild(shortCard);
        });
    } else {
        shortsContainer.innerHTML = '<p>Aucun short n\'a été généré.</p>';
    }
    
    showNotification('Traitement terminé avec succès!', 'success');
}

// Annuler une tâche
function cancelTask() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
    
    resetUI();
    showNotification('Traitement annulé.', 'warning');
}

// Réinitialiser l'interface
function resetUI() {
    // Réinitialiser les sections
    uploadSection.style.display = 'block';
    progressSection.style.display = 'none';
    resultsSection.style.display = 'none';
    
    // Réinitialiser la progression
    progressBar.style.width = '0%';
    progressMessage.textContent = 'Initialisation...';
    
    // Réinitialiser les variables d'état
    currentTaskId = null;
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
}

// Notifications
function showNotification(message, type = 'error') {
    notificationMessage.textContent = message;
    notification.className = 'notification';
    notification.classList.add(type);
    notification.style.display = 'flex';
    
    // Auto-hide après 5 secondes
    setTimeout(() => {
        closeNotification();
    }, 5000);
}

function closeNotification() {
    notification.style.display = 'none';
}

// Utilitaires
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}