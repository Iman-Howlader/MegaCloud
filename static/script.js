// Global elements
const globalSpinner = document.createElement('div');
globalSpinner.className = 'global-spinner';
globalSpinner.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
document.body.appendChild(globalSpinner);

let currentPreviewUrl = null;
let currentPreviewFile = null;
let currentObjectUrl = null;

// Utility Functions
function showSpinner() {
    globalSpinner.style.display = 'flex';
}

function hideSpinner() {
    globalSpinner.style.display = 'none';
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function showMessage(message, type) {
    const toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        console.error('Toast container not found in DOM');
        return;
    }

    const toast = document.createElement('div');
    toast.classList.add('toast', 'align-items-center', `text-bg-${type === 'success' ? 'success' : 'danger'}`, 'border-0');
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return 'fas fa-image';
    if (['pdf'].includes(ext)) return 'fas fa-file-pdf';
    if (['doc', 'docx'].includes(ext)) return 'fas fa-file-word';
    if (['xls', 'xlsx'].includes(ext)) return 'fas fa-file-excel';
    if (['ppt', 'pptx'].includes(ext)) return 'fas fa-file-powerpoint';
    if (['zip', 'rar', '7z'].includes(ext)) return 'fas fa-file-archive';
    if (['mp3', 'wav', 'ogg'].includes(ext)) return 'fas fa-file-audio';
    if (['mp4', 'mov', 'avi'].includes(ext)) return 'fas fa-file-video';
    if (['txt', 'csv', 'json', 'xml'].includes(ext)) return 'fas fa-file-alt';
    return 'fas fa-file';
}

function initTheme() {
    const themeButton = document.getElementById('theme-toggle');
    if (!themeButton) return;
    
    const themeIcon = themeButton.querySelector('i');
    const savedTheme = localStorage.getItem('theme') || 'light';

    if (savedTheme === 'dark') {
        document.body.classList.remove('light-mode');
        document.body.classList.add('dark-mode');
        if (themeIcon) themeIcon.classList.replace('fa-sun', 'fa-moon');
    } else {
        document.body.classList.add('light-mode');
        document.body.classList.remove('dark-mode');
        if (themeIcon) themeIcon.classList.replace('fa-moon', 'fa-sun');
    }

    themeButton.addEventListener('click', () => {
        if (document.body.classList.contains('light-mode')) {
            document.body.classList.remove('light-mode');
            document.body.classList.add('dark-mode');
            if (themeIcon) themeIcon.classList.replace('fa-sun', 'fa-moon');
            localStorage.setItem('theme', 'dark');
        } else {
            document.body.classList.add('light-mode');
            document.body.classList.remove('dark-mode');
            if (themeIcon) themeIcon.classList.replace('fa-moon', 'fa-sun');
            localStorage.setItem('theme', 'light');
        }
    });
}

async function requestOTP() {
    const email = document.getElementById('email').value;
    if (!validateEmail(email)) {
        showMessage("Please enter a valid email.", "error");
        return;
    }
    showSpinner();
    try {
        const response = await fetch('/request_otp', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ email }) 
        });
        const result = await response.json();
        if (response.ok) {
            document.getElementById('otp-section').style.display = 'block';
            document.getElementById('email-section').style.display = 'none';
            showMessage(result.message, "success");
        } else {
            showMessage(result.error, "error");
        }
    } catch (error) {
        showMessage("An error occurred.", "error");
    } finally {
        hideSpinner();
    }
}

async function verifyOTP() {
    const otp = document.getElementById('otp').value;
    if (!otp) {
        showMessage("Please enter the OTP.", "error");
        return;
    }
    showSpinner();
    try {
        const response = await fetch('/verify_otp', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ otp }) 
        });
        const result = await response.json();
        if (response.ok) {
            window.location.href = result.redirect || '/dashboard';
        } else {
            showMessage(result.error, "error");
        }
    } catch (error) {
        showMessage("Verification failed.", "error");
    } finally {
        hideSpinner();
    }
}

async function logout() {
    showSpinner();
    try {
        await fetch('/logout');
        window.location.href = '/';
    } catch (error) {
        showMessage("Logout failed.", "error");
    } finally {
        hideSpinner();
    }
}

async function uploadFile(files) {
    if (!files || files.length === 0) {
        showMessage("No file selected!", "error");
        return;
    }
    
    showSpinner();
    const formData = new FormData();
    formData.append('file', files[0]);
    
    const progressBar = document.querySelector('#uploadProgress .progress-bar');
    document.getElementById('uploadProgress').classList.remove('d-none');
    progressBar.style.width = '0%';
    
    try {
        const response = await fetch('/upload', { 
            method: 'POST', 
            body: formData,
            credentials: 'include'
        });
        const result = await response.json();
        
        progressBar.style.width = '100%';
        setTimeout(() => {
            document.getElementById('uploadProgress').classList.add('d-none');
            const uploadModal = bootstrap.Modal.getInstance(document.getElementById('uploadModal'));
            if (uploadModal) uploadModal.hide();
        }, 500);
        
        if (response.ok) {
            showMessage(result.message, "success");
            await listFiles();
            await updateStats();
        } else {
            showMessage(result.error, "error");
        }
    } catch (error) {
        showMessage("Upload failed: " + error.message, "error");
    } finally {
        hideSpinner();
    }
}

async function listFiles(category = 'All') {
    showSpinner();
    try {
        const response = await fetch('/list_files');
        const result = await response.json();
        
        if (result.error) {
            showMessage(result.error, "error");
            return;
        }
        
        let files = category === 'All' ? result.files : result.categorized[category] || [];
        const fileList = document.getElementById('file-list');
        
        fileList.innerHTML = files.map(file => `
            <div class="file-item">
                <i class="${getFileIcon(file.display_filename)} file-icon"></i>
                <div class="flex-grow-1">
                    <span>${file.display_filename}</span>
                    <small class="d-block text-muted">${file.size_mb.toFixed(2)} MB</small>
                </div>
                <div>
                    <button class="btn btn-sm btn-primary mx-1" onclick="previewFile('${file.file_id}')">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-primary mx-1" onclick="downloadFile('${file.file_id}')">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn btn-sm btn-danger mx-1" onclick="deleteFile('${file.file_id}', '${file.display_filename}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
        document.getElementById('file-count').textContent = `${files.length} files`;
    } catch (error) {
        showMessage("Failed to fetch files.", "error");
    } finally {
        hideSpinner();
    }
}

async function searchFiles() {
    const query = document.getElementById('searchInput').value;
    showSpinner();
    try {
        const response = await fetch(`/search_files?query=${encodeURIComponent(query)}`);
        const result = await response.json();
        
        if (result.error) {
            showMessage(result.error, "error");
            return;
        }
        
        const fileList = document.getElementById('file-list');
        fileList.innerHTML = result.files.map(file => `
            <div class="file-item">
                <i class="${getFileIcon(file.display_filename)} file-icon"></i>
                <div class="flex-grow-1">
                    <span>${file.display_filename}</span>
                    <small class="d-block text-muted">${file.size_mb.toFixed(2)} MB</small>
                </div>
                <div>
                    <button class="btn btn-sm btn-primary mx-1" onclick="previewFile('${file.file_id}')">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-primary mx-1" onclick="downloadFile('${file.file_id}')">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn btn-sm btn-danger mx-1" onclick="deleteFile('${file.file_id}', '${file.display_filename}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
        document.getElementById('file-count').textContent = `${result.files.length} files`;
    } catch (error) {
        showMessage("Failed to search files.", "error");
    } finally {
        hideSpinner();
    }
}

async function updateStats() {
    showSpinner();
    try {
        const response = await fetch('/stats', { credentials: 'include' });
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const result = await response.json();
        
        console.log('Stats response:', result);
        
        if (result.success) {
            const storageUsed = document.getElementById('storage-used');
            const totalFiles = document.getElementById('total-files');
            
            if (!storageUsed || !totalFiles) {
                console.error('Missing DOM elements:', { storageUsed: !!storageUsed, totalFiles: !!totalFiles });
                throw new Error('Stats elements missing in DOM');
            }
            
            storageUsed.textContent = `${result.storage_used.toFixed(2)} MB`;
            totalFiles.textContent = result.total_files;
        } else {
            throw new Error(result.error || 'Stats response indicated failure');
        }
    } catch (error) {
        console.error('Update stats failed:', error.message);
        showMessage(`Failed to fetch stats: ${error.message}`, 'error');
    } finally {
        hideSpinner();
    }
}

async function previewFile(fileId) {
    showSpinner();
    document.getElementById('preview-overlay').style.display = 'flex';
    const previewContent = document.getElementById('preview-content');
    const downloadBtn = document.getElementById('download-preview-btn');
    
    try {
        const response = await fetch(`/preview/${fileId}`, { credentials: 'include' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Preview failed');
        }
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const mimeType = response.headers.get('Content-Type') || 'application/octet-stream';
        
        const fileListResponse = await fetch('/list_files');
        const fileList = await fileListResponse.json();
        const file = fileList.files.find(f => f.file_id === fileId);
        const displayFilename = file ? file.display_filename : 'Unknown File';
        
        document.getElementById('preview-title').textContent = displayFilename;
        
        previewContent.innerHTML = '';
        downloadBtn.style.display = 'none';
        
        console.log(`Preview MIME type: ${mimeType}`); // Debug log
        
        if (mimeType.startsWith('image/')) {
            previewContent.innerHTML = `<img src="${url}" class="img-fluid" alt="${displayFilename}">`;
        } else if (mimeType === 'application/pdf') {
            previewContent.innerHTML = `<embed src="${url}" type="application/pdf" width="100%" height="600px">`;
        } else if (mimeType.startsWith('video/')) {
            previewContent.innerHTML = `
                <video controls width="100%" height="auto">
                    <source src="${url}" type="${mimeType}">
                    Your browser does not support the video tag.
                </video>`;
        } else if (mimeType.startsWith('audio/')) {
            previewContent.innerHTML = `
                <audio controls>
                    <source src="${url}" type="${mimeType}">
                    Your browser does not support the audio element.
                </audio>`;
        } else if (mimeType === 'text/plain') {
            const text = await blob.text();
            previewContent.innerHTML = `<pre>${text}</pre>`;
        } else {
            previewContent.innerHTML = '<p>Preview not available for this file type.</p>';
            downloadBtn.style.display = 'inline-block';
            downloadBtn.onclick = () => downloadFile(fileId);
        }
        
        previewContent.style.display = 'block';
        previewContent.dataset.previewUrl = url;
        currentPreviewFile = displayFilename;
    } catch (error) {
        showMessage('Failed to load preview: ' + error.message, 'error');
        closePreview();
    } finally {
        hideSpinner();
    }
}

function closePreview() {
    const previewOverlay = document.getElementById('preview-overlay');
    const previewContent = document.getElementById('preview-content');
    
    if (previewContent.dataset.previewUrl) {
        URL.revokeObjectURL(previewContent.dataset.previewUrl);
        delete previewContent.dataset.previewUrl;
    }
    
    if (currentPreviewFile) {
        fetch(`/cleanup_preview/${encodeURIComponent(currentPreviewFile)}`, {
            method: 'POST',
            credentials: 'include'
        }).then(response => response.json())
          .then(result => {
              if (result.success) {
                  console.log('Preview file cleaned up');
              } else {
                  console.error('Cleanup failed:', result.error);
              }
          })
          .catch(error => console.error('Error during cleanup:', error));
        currentPreviewFile = null;
    }
    
    previewOverlay.style.display = 'none';
    previewContent.style.display = 'none';
    previewContent.innerHTML = '';
    document.getElementById('download-preview-btn').style.display = 'none';
}

async function downloadFile(fileId) {
    showSpinner();
    try {
        const response = await fetch(`/download/${fileId}`, { credentials: 'include' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Download failed');
        }
        
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        
        // Fetch file list to get the display filename
        const fileListResponse = await fetch('/list_files');
        const fileList = await fileListResponse.json();
        const file = fileList.files.find(f => f.file_id === fileId);
        const displayFilename = file ? file.display_filename : 'downloaded_file';
        
        const a = document.createElement('a');
        a.href = url;
        a.download = displayFilename;
        document.body.appendChild(a);
        a.click();
        
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
        
        showMessage(`"${displayFilename}" downloaded successfully`, "success");
    } catch (error) {
        showMessage("Download failed: " + error.message, "error");
    } finally {
        hideSpinner();
    }
}

async function deleteFile(fileId, displayFilename) {
    if (!confirm(`Are you sure you want to delete "${displayFilename}"?`)) return;
    
    showSpinner();
    try {
        const response = await fetch(`/delete/${fileId}`, { method: 'DELETE', credentials: 'include' });
        const result = await response.json();
        
        if (response.ok) {
            showMessage(`"${displayFilename}" deleted successfully`, "success");
            await listFiles();
            await updateStats();
        } else {
            showMessage(result.error || "Deletion failed", "error");
        }
    } catch (error) {
        showMessage("Deletion failed: " + error.message, "error");
    } finally {
        hideSpinner();
    }
}

function initDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight() {
        dropZone.classList.add('dragover');
    }
    
    function unhighlight() {
        dropZone.classList.remove('dragover');
    }
    
    dropZone.addEventListener('drop', handleDrop, false);
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        uploadFile(files);
    }
}

function initFileInput() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput) return;
    
    fileInput.addEventListener('change', (e) => {
        uploadFile(e.target.files);
        e.target.value = '';
    });
}

function initDashboard() {
    if (window.location.pathname === '/dashboard') {
        listFiles();
        updateStats();
    }
}

function initEventListeners() {
    document.querySelectorAll('.category-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const category = btn.dataset.category;
            listFiles(category);
            document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
    
    const searchBtn = document.getElementById('searchBtn');
    if (searchBtn) searchBtn.addEventListener('click', searchFiles);
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') searchFiles();
        });
    }
}

function showPreviewOverlay() {
    document.getElementById('preview-overlay').style.display = 'flex';
    document.body.classList.add('preview-open');
}

function hidePreviewOverlay() {
    document.getElementById('preview-overlay').style.display = 'none';
    document.body.classList.remove('preview-open');
    cleanupPreview();
}

function cleanupPreview() {
    if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = null;
    }
    if (currentPreviewFile) currentPreviewFile = null;
    if (currentPreviewUrl) {
        URL.revokeObjectURL(currentPreviewUrl);
        currentPreviewUrl = null;
    }
    document.getElementById('preview-content').innerHTML = '';
}

document.addEventListener('DOMContentLoaded', () => {
    initDragAndDrop();
    initFileInput();
    initDashboard();
    initEventListeners();
    initTheme();
});

document.getElementById('preview-overlay').addEventListener('click', function(e) {
    if (e.target === this) closePreview();
});