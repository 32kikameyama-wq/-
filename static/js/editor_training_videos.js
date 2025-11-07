function openTrainingVideoModal() {
    const modal = document.getElementById('trainingVideoModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.focus();
    }
}

function closeTrainingVideoModal() {
    const modal = document.getElementById('trainingVideoModal');
    if (modal) {
        modal.style.display = 'none';
        const form = document.getElementById('trainingVideoForm');
        if (form) {
            form.reset();
        }
    }
}

function showProgressMessage(card, message, isError = false) {
    if (!card) return;
    const messageElement = card.querySelector('[data-role="message"]');
    if (!messageElement) return;
    messageElement.textContent = message;
    messageElement.classList.toggle('error', isError);
    if (message) {
        setTimeout(() => {
            if (messageElement.textContent === message) {
                messageElement.textContent = '';
                messageElement.classList.remove('error');
            }
        }, 4000);
    }
}

function updateTrainingCard(card, data) {
    if (!card || !data) return;

    const progressFill = card.querySelector('.progress-fill');
    if (progressFill) {
        progressFill.style.width = `${data.user_progress}%`;
    }

    const progressValue = card.querySelector('.progress-value');
    if (progressValue) {
        progressValue.textContent = `${data.user_progress}%`;
    }

    const progressInput = card.querySelector('.training-progress-input');
    if (progressInput) {
        progressInput.value = data.user_progress;
    }

    const statusSelect = card.querySelector('.training-status-select');
    if (statusSelect) {
        statusSelect.value = data.user_status;
    }

    const notesField = card.querySelector('.training-notes-input');
    if (notesField) {
        notesField.value = data.user_notes || '';
    }

    const lastViewed = card.querySelector('.last-viewed-value');
    if (lastViewed) {
        lastViewed.textContent = data.user_last_viewed || '---';
    }

    if (window.trainingVideoPage && window.trainingVideoPage.includeWatchers) {
        const summary = card.querySelector('.training-stats');
        if (summary) {
            summary.querySelectorAll('span')[2].textContent = `視聴者: ${data.total_viewers}名 / 完了 ${data.completed_viewers}名`;
            summary.querySelectorAll('span')[3].textContent = `平均進捗: ${data.avg_progress}%`;
        }

        const watchersPanel = card.querySelector('.watchers-panel');
        if (watchersPanel) {
            const existingTable = watchersPanel.querySelector('.watchers-table');
            const emptyMessage = watchersPanel.querySelector('.empty');
            if (existingTable) {
                existingTable.remove();
            }
            if (emptyMessage) {
                emptyMessage.remove();
            }
            if (data.watchers && data.watchers.length > 0) {
                const table = document.createElement('table');
                table.className = 'watchers-table';
                table.innerHTML = `
                    <thead>
                        <tr>
                            <th>編集者</th>
                            <th>状態</th>
                            <th>進捗</th>
                            <th>最終視聴</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.watchers.map(watcher => `
                            <tr>
                                <td>${watcher.name}</td>
                                <td>${watcher.status}</td>
                                <td>${watcher.progress_percent}%</td>
                                <td>${watcher.last_viewed_at || '---'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                `;
                watchersPanel.appendChild(table);
            } else {
                const empty = document.createElement('p');
                empty.className = 'empty';
                empty.textContent = 'まだ視聴したメンバーはいません。';
                watchersPanel.appendChild(empty);
            }
        }
    }
}

async function handleProgressSave(event) {
    const button = event.currentTarget;
    const videoId = button.getAttribute('data-video-id');
    const card = button.closest('.training-card');
    if (!videoId || !card) return;

    const statusSelect = card.querySelector('.training-status-select');
    const progressInput = card.querySelector('.training-progress-input');
    const notesInput = card.querySelector('.training-notes-input');

    const status = statusSelect ? statusSelect.value : '視聴中';
    const progressValue = progressInput ? parseInt(progressInput.value, 10) : 0;
    const notes = notesInput ? notesInput.value.trim() : '';

    if (Number.isNaN(progressValue) || progressValue < 0 || progressValue > 100) {
        showProgressMessage(card, '進捗は0〜100の範囲で入力してください。', true);
        return;
    }

    try {
        button.disabled = true;
        showProgressMessage(card, '更新中...');
        const response = await fetch(`/api/editor/training-videos/${videoId}/progress`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                status,
                progress_percent: progressValue,
                notes
            })
        });

        const result = await response.json();
        if (!response.ok || result.status !== 'success') {
            const message = result && result.message ? result.message : '更新に失敗しました。';
            throw new Error(message);
        }

        updateTrainingCard(card, result.data);
        showProgressMessage(card, '進捗を保存しました。');
    } catch (error) {
        console.error(error);
        showProgressMessage(card, error.message || '更新に失敗しました。', true);
    } finally {
        button.disabled = false;
    }
}

async function handleTrainingVideoCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const payload = {
        title: formData.get('title')?.trim() || '',
        url: formData.get('url')?.trim() || '',
        description: formData.get('description')?.trim() || '',
        duration_minutes: formData.get('duration') ? parseInt(formData.get('duration'), 10) : null
    };

    if (payload.duration_minutes !== null && (Number.isNaN(payload.duration_minutes) || payload.duration_minutes < 0)) {
        alert('想定視聴時間は0以上の数値で入力してください。');
        return;
    }

    try {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = true;

        const response = await fetch('/api/admin/training-videos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (!response.ok || result.status !== 'success') {
            const message = result && result.message ? result.message : '登録に失敗しました。';
            throw new Error(message);
        }

        closeTrainingVideoModal();
        window.location.reload();
    } catch (error) {
        console.error(error);
        alert(error.message || '登録に失敗しました。');
    } finally {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-action="save-progress"]').forEach(button => {
        button.addEventListener('click', handleProgressSave);
    });

    const modal = document.getElementById('trainingVideoModal');
    if (modal) {
        modal.addEventListener('click', closeTrainingVideoModal);
    }

    const form = document.getElementById('trainingVideoForm');
    if (form) {
        form.addEventListener('submit', handleTrainingVideoCreate);
    }
});

window.openTrainingVideoModal = openTrainingVideoModal;
window.closeTrainingVideoModal = closeTrainingVideoModal;

