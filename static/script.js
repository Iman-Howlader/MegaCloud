document.addEventListener('DOMContentLoaded', () => {
    // Retrieve CSRF token safely
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        showNotification('CSRF token missing. Some features may not work.', 'danger');
    }

    initializeForms();
    if (window.location.pathname === '/dashboard') {
        loadStats();
        listFiles('All');
        loadStorageAccounts();
        checkStorageCallback();
    }
});

// Helper function to retrieve CSRF token
function getCsrfToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : null;
}

// Helper function to create fetch headers with CSRF token
function getFetchHeaders(method, isJson = false) {
    const headers = { 'X-CSRF-Token': getCsrfToken() };
    if (isJson) {
        headers['Content-Type'] = 'application/json';
    }
    return headers;
}

function initializeForms() {
    initializeRegisterForm();
    initializeVerifyRegisterForm();
    initializeRequestOtpForm();
    initializeVerifyOtpForm();
    initializeUploadForm();
    initializeAddStorageForm();
}

function showNotification(message, type = 'success') {
    const container = document.querySelector('.notification-container');
    if (!container) return;
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function initializeRegisterForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: getFetchHeaders('POST', true),
                body: JSON.stringify(data)
            });
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                if (responseData.redirect) {
                    setTimeout(() => window.location.href = responseData.redirect, 1000);
                }
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Registration failed: ' + error.message, 'danger');
        }
    });
}

function initializeVerifyRegisterForm() {
    const form = document.getElementById('verifyRegisterForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        const data = { otp: formData.get('otp') };
        try {
            const response = await fetch('/verify_register', {
                method: 'POST',
                headers: getFetchHeaders('POST', true),
                body: JSON.stringify(data)
            });
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                console.error('Non-JSON response:', text);
                throw new Error('Server returned an unexpected response format');
            }
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                if (responseData.redirect) {
                    setTimeout(() => window.location.href = responseData.redirect, 1000);
                }
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Verification failed: ' + error.message, 'danger');
        }
    });
}

function resendOTP() {
    const identifier = sessionStorage.getItem('identifier');
    if (!identifier) {
        showNotification('Please enter your email or username first.', 'warning');
        return;
    }
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch('/request_otp', {
        method: 'POST',
        headers: getFetchHeaders('POST', true),
        body: JSON.stringify({ identifier })
    })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message || data.error, data.message ? 'success' : 'danger');
        })
        .catch(error => {
            showNotification('Failed to resend OTP: ' + error.message, 'danger');
        });
}

function initializeRequestOtpForm() {
    const form = document.getElementById('requestOtpForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        const data = { identifier: formData.get('identifier') };
        sessionStorage.setItem('identifier', data.identifier);
        try {
            const response = await fetch('/request_otp', {
                method: 'POST',
                headers: getFetchHeaders('POST', true),
                body: JSON.stringify(data)
            });
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                const modal = new bootstrap.Modal(document.getElementById('verifyOtpModal'));
                modal.show();
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Failed to request OTP: ' + error.message, 'danger');
        }
    });
}

function initializeVerifyOtpForm() {
    const form = document.getElementById('verifyOtpForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        const data = { otp: formData.get('otp') };
        try {
            const response = await fetch('/verify_otp', {
                method: 'POST',
                headers: getFetchHeaders('POST', true),
                body: JSON.stringify(data)
            });
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                console.error('Non-JSON response:', text);
                throw new Error('Server returned an unexpected response format');
            }
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                if (responseData.redirect) {
                    setTimeout(() => window.location.href = responseData.redirect, 1000);
                }
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Verification failed: ' + error.message, 'danger');
        }
    });
}

function initializeUploadForm() {
    const form = document.getElementById('uploadForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData,
                headers: getFetchHeaders('POST')
            });
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                bootstrap.Modal.getInstance(document.getElementById('uploadModal')).hide();
                form.reset();
                loadStats();
                listFiles('All');
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Upload failed: ' + error.message, 'danger');
        }
    });
}

function initializeAddStorageForm() {
    const form = document.getElementById('addStorageForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!getCsrfToken()) {
            showNotification('CSRF token missing. Please refresh the page.', 'danger');
            return;
        }
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        try {
            const response = await fetch('/storage_accounts', {
                method: 'POST',
                headers: getFetchHeaders('POST', true),
                body: JSON.stringify(data)
            });
            const responseData = await response.json();
            if (response.ok) {
                showNotification(responseData.message, 'success');
                if (responseData.auth_url) {
                    window.location.href = responseData.auth_url;
                }
            } else {
                showNotification(responseData.error, 'danger');
            }
        } catch (error) {
            showNotification('Failed to add storage account: ' + error.message, 'danger');
        }
    });
}

function checkStorageCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const status = urlParams.get('storage');
    if (status === 'connected') {
        showNotification('Storage account connected successfully!', 'success');
        loadStorageAccounts();
        loadStats();
    } else if (status === 'failed') {
        showNotification('Failed to connect storage account.', 'danger');
        loadStorageAccounts();
    }
}

function loadStats() {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch('/stats', {
        headers: getFetchHeaders('GET')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('storage-used').textContent = data.storage_used.toFixed(2);
                document.getElementById('total-files').textContent = data.total_files;
                document.getElementById('totalStorage').textContent = data.total_size_mb.toFixed(2);
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to load stats: ' + error.message, 'danger');
        });
}

function listFiles(category = 'All') {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch('/list_files', {
        headers: getFetchHeaders('GET')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const fileList = document.getElementById('fileList');
                fileList.innerHTML = '';
                const files = category === 'All' ? data.files : data.categorized[category] || [];
                if (files.length === 0) {
                    fileList.innerHTML = '<p class="text-muted">No files found.</p>';
                    return;
                }
                files.forEach(file => {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'file-item';
                    fileItem.innerHTML = `
                    <div>
                        <i class="fas ${getFileIcon(file.category)} me-2"></i>
                        ${file.display_filename} (${file.size_mb.toFixed(2)} MB)
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-sm btn-outline-primary" onclick="previewFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-eye"></i></button>
                        <button class="btn btn-sm btn-outline-success" onclick="downloadFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-download"></i></button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-trash"></i></button>
                    </div>
                `;
                    fileList.appendChild(fileItem);
                });
                updateNavLinks(category);
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to list files: ' + error.message, 'danger');
        });
}

function getFileIcon(category) {
    const icons = {
        Images: 'fa-image',
        Documents: 'fa-file-alt',
        Videos: 'fa-video',
        Audio: 'fa-music',
        Other: 'fa-file'
    };
    return icons[category] || 'fa-file';
}

function updateNavLinks(activeCategory) {
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.classList.remove('active');
        if (link.textContent.includes(activeCategory)) {
            link.classList.add('active');
        }
    });
}

function searchFiles() {
    const query = document.getElementById('searchInput').value;
    if (!query) {
        listFiles('All');
        return;
    }
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch(`/search_files?query=${encodeURIComponent(query)}`, {
        headers: getFetchHeaders('GET')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const fileList = document.getElementById('fileList');
                fileList.innerHTML = '';
                if (data.files.length === 0) {
                    fileList.innerHTML = '<p class="text-muted">No files found.</p>';
                    return;
                }
                data.files.forEach(file => {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'file-item';
                    fileItem.innerHTML = `
                    <div>
                        <i class="fas ${getFileIcon(file.category)} me-2"></i>
                        ${file.display_filename} (${file.size_mb.toFixed(2)} MB)
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-sm btn-outline-primary" onclick="previewFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-eye"></i></button>
                        <button class="btn btn-sm btn-outline-success" onclick="downloadFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-download"></i></button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteFile('${file.file_id}', '${file.display_filename}')"><i class="fas fa-trash"></i></button>
                    </div>
                `;
                    fileList.appendChild(fileItem);
                });
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to search files: ' + error.message, 'danger');
        });
}

function previewFile(fileId, filename) {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    window.open(`/preview/${fileId}`, '_blank');
    setTimeout(() => {
        fetch(`/cleanup_preview/${encodeURIComponent(filename)}`, {
            method: 'POST',
            headers: getFetchHeaders('POST')
        })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    console.warn('Preview cleanup failed:', data.error);
                }
            })
            .catch(error => {
                console.error('Preview cleanup failed:', error);
            });
    }, 60000);
}

function downloadFile(fileId, filename) {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    const link = document.createElement('a');
    link.href = `/download/${fileId}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => {
        fetch(`/cleanup_download/${encodeURIComponent(filename)}`, {
            method: 'POST',
            headers: getFetchHeaders('POST')
        })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    console.warn('Download cleanup failed:', data.error);
                }
            })
            .catch(error => {
                console.error('Download cleanup failed:', error);
            });
    }, 60000);
}

function deleteFile(fileId, filename) {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) return;
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch(`/delete/${fileId}`, {
        method: 'DELETE',
        headers: getFetchHeaders('DELETE')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(data.message, 'success');
                loadStats();
                listFiles('All');
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to delete file: ' + error.message, 'danger');
        });
}

function loadStorageAccounts() {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch('/storage_accounts', {
        headers: getFetchHeaders('GET')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const tableBody = document.getElementById('storageAccountsTable');
                tableBody.innerHTML = '';
                data.storage_accounts.forEach(account => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                    <td>${account.provider_type.replace('_', ' ').toUpperCase()}</td>
                    <td>${account.email}</td>
                    <td>${account.status}</td>
                    <td>${account.free_mb.toFixed(2)} MB free / ${account.total_mb.toFixed(2)} MB</td>
                    <td>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteStorageAccount('${account.id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                `;
                    tableBody.appendChild(row);
                });
                document.getElementById('totalStorage').textContent = data.total_storage.toFixed(2);
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to load storage accounts: ' + error.message, 'danger');
        });
}

function deleteStorageAccount(accountId) {
    if (!confirm('Are you sure you want to delete this storage account?')) return;
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch(`/storage_accounts?account_id=${accountId}`, {
        method: 'DELETE',
        headers: getFetchHeaders('DELETE')
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(data.message, 'success');
                loadStorageAccounts();
                loadStats();
            } else {
                showNotification(data.error, 'danger');
            }
        })
        .catch(error => {
            showNotification('Failed to delete storage account: ' + error.message, 'danger');
        });
}

function logout() {
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }
    fetch('/logout', {
        headers: getFetchHeaders('GET')
    })
        .then(response => response.json())
        .then(data => {
            if (data.redirect) {
                window.location.href = data.redirect;
            }
        })
        .catch(error => {
            showNotification('Logout failed: ' + error.message, 'danger');
        });
}

function toggleAIChat() {
    const aiChatContainer = document.getElementById('aiChatContainer');
    aiChatContainer.style.display = aiChatContainer.style.display === 'none' ? 'flex' : 'none';
    if (aiChatContainer.style.display === 'flex') {
        document.getElementById('aiQueryInput').focus();
    }
}

function sendAIQuery() {
    const queryInput = document.getElementById('aiQueryInput');
    const query = queryInput.value.trim();
    if (!query) return;
    if (!getCsrfToken()) {
        showNotification('CSRF token missing. Please refresh the page.', 'danger');
        return;
    }

    const chatBody = document.getElementById('aiChatBody');
    const userMessage = document.createElement('div');
    userMessage.className = 'message user-message';
    userMessage.textContent = query;
    chatBody.appendChild(userMessage);
    chatBody.scrollTop = chatBody.scrollHeight;

    fetch('/ai/ask', {
        method: 'POST',
        headers: getFetchHeaders('POST', true),
        body: JSON.stringify({ question: query })
    })
    .then(response => {
        console.log('AI query response status:', response.status);
        return response.json();
    })
    .then(data => {
        if (data.success) {
            const aiMessage = document.createElement('div');
            aiMessage.className = 'message ai-message';
            aiMessage.innerHTML = marked.parse(data.answer);
            chatBody.appendChild(aiMessage);
            chatBody.scrollTop = chatBody.scrollHeight;
        } else {
            showNotification(data.error, 'danger');
        }
    })
    .catch(error => {
        console.error('AI query error:', error);
        showNotification('AI query failed: ' + error.message, 'danger');
    });

    queryInput.value = '';
}