document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('adminTrainingForm');
    const message = document.getElementById('adminTrainingMessage');
    const editModal = document.getElementById('trainingEditModal');
    const editForm = document.getElementById('adminTrainingEditForm');
    const editMessage = document.getElementById('adminTrainingEditMessage');
    let editingVideoId = null;

    const resetEditForm = () => {
        if (!editForm) return;
        editForm.reset();
        const fileInput = editForm.querySelector('input[type="file"]');
        if (fileInput) {
            fileInput.value = '';
        }
    };

    const toggleModal = (modal, shouldOpen) => {
        if (!modal) return;
        const willOpen = shouldOpen === undefined ? !modal.classList.contains('open') : shouldOpen;
        if (willOpen) {
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
        } else {
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
            resetEditForm();
            editingVideoId = null;
            if (editMessage) {
                editMessage.textContent = '';
                editMessage.classList.remove('error');
            }
        }
    };

    const decodeDatasetValue = (value) => {
        if (!value) return '';
        return value.replace(/&#10;/g, '\n');
    };

    document.querySelectorAll('[data-close-target]').forEach((element) => {
        element.addEventListener('click', (event) => {
            const targetId = element.getAttribute('data-close-target');
            if (!targetId) return;
            const modal = document.getElementById(targetId);
            if (!modal) return;
            if (event.target === element || element.classList.contains('gantt-modal-close') || element.classList.contains('btn')) {
                toggleModal(modal, false);
            }
        });
    });

    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            const submitButton = form.querySelector('button[type="submit"]');
            const formData = new FormData(form);

            const title = (formData.get('title') || '').trim();
            if (!title) {
                if (message) {
                    message.textContent = 'タイトルは必須です。';
                    message.classList.add('error');
                }
                return;
            }
            formData.set('title', title);

            const urlValue = (formData.get('url') || '').trim();
            if (urlValue) {
                formData.set('url', urlValue);
            } else {
                formData.delete('url');
            }

            const durationValue = formData.get('duration_minutes');
            if (durationValue !== null && durationValue !== '') {
                formData.set('duration_minutes', durationValue);
            } else {
                formData.delete('duration_minutes');
            }

            try {
                if (submitButton) {
                    submitButton.disabled = true;
                }
                if (message) {
                    message.textContent = '登録中...';
                    message.classList.remove('error');
                }

                const response = await fetch('/api/admin/training-videos', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                if (!response.ok || result.status !== 'success') {
                    const errorMessage = result && result.message ? result.message : '登録に失敗しました。';
                    throw new Error(errorMessage);
                }

                if (message) {
                    message.textContent = '動画を登録しました。ページを更新しています...';
                    message.classList.remove('error');
                }
                form.reset();
                setTimeout(() => window.location.reload(), 600);
            } catch (error) {
                console.error(error);
                if (message) {
                    message.textContent = error.message || '登録に失敗しました。';
                    message.classList.add('error');
                } else {
                    alert(error.message || '登録に失敗しました。');
                }
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                }
            }
        });
    }

    const populateEditModal = (card) => {
        if (!card || !editForm) return;

        const titleField = editForm.querySelector('#edit_training_title');
        const urlField = editForm.querySelector('#edit_training_url');
        const durationField = editForm.querySelector('#edit_training_duration');
        const descriptionField = editForm.querySelector('#edit_training_description');

        const dataset = card.dataset || {};
        const title = decodeDatasetValue(dataset.videoTitle) || card.querySelector('h3')?.textContent?.trim() || '';
        const url = dataset.videoUrl || card.querySelector('.training-meta a')?.getAttribute('href') || '';
        const duration = dataset.videoDuration || '';
        const description = decodeDatasetValue(dataset.videoDescription) || card.querySelector('.training-description')?.textContent?.trim() || '';

        if (titleField) titleField.value = title;
        if (urlField) urlField.value = url;
        if (durationField) durationField.value = duration;
        if (descriptionField) descriptionField.value = description;

        const fileInput = editForm.querySelector('#edit_training_file');
        if (fileInput) fileInput.value = '';
    };

    const editButtons = document.querySelectorAll('.btn-edit-training');
    editButtons.forEach((button) => {
        button.addEventListener('click', (event) => {
            const card = event.currentTarget.closest('.training-card');
            if (!card) return;
            editingVideoId = card.getAttribute('data-video-id');
            populateEditModal(card);
            toggleModal(editModal, true);
        });
    });

    if (editForm) {
        editForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!editingVideoId) return;

            const submitButton = editForm.querySelector('button[type="submit"]');
            const formData = new FormData(editForm);

            const title = (formData.get('title') || '').trim();
            if (!title) {
                if (editMessage) {
                    editMessage.textContent = 'タイトルは必須です。';
                    editMessage.classList.add('error');
                }
                return;
            }
            formData.set('title', title);

            const urlValue = (formData.get('url') || '').trim();
            if (urlValue) {
                formData.set('url', urlValue);
            } else {
                formData.delete('url');
            }

            const durationValue = formData.get('duration_minutes');
            if (durationValue === null || durationValue === '') {
                formData.delete('duration_minutes');
            } else {
                formData.set('duration_minutes', durationValue);
            }

            try {
                if (submitButton) submitButton.disabled = true;
                if (editMessage) {
                    editMessage.textContent = '更新中...';
                    editMessage.classList.remove('error');
                }

                const response = await fetch(`/api/admin/training-videos/${editingVideoId}`, {
                    method: 'PUT',
                    body: formData
                });

                const result = await response.json();
                if (!response.ok || result.status !== 'success') {
                    const errorMessage = result && result.message ? result.message : '更新に失敗しました。';
                    throw new Error(errorMessage);
                }

                if (editMessage) {
                    editMessage.textContent = '動画を更新しました。ページを更新しています...';
                    editMessage.classList.remove('error');
                }
                setTimeout(() => window.location.reload(), 600);
            } catch (error) {
                console.error(error);
                const displayMessage = error && error.message ? error.message : '更新に失敗しました。';
                if (editMessage) {
                    editMessage.textContent = displayMessage;
                    editMessage.classList.add('error');
                } else {
                    alert(displayMessage);
                }
            } finally {
                if (submitButton) submitButton.disabled = false;
            }
        });
    }

    const deleteButtons = document.querySelectorAll('.btn-delete-training');
    deleteButtons.forEach((button) => {
        button.addEventListener('click', async (event) => {
            const card = event.currentTarget.closest('.training-card');
            if (!card) return;
            const videoId = card.getAttribute('data-video-id');
            const titleValue = decodeDatasetValue(card.dataset.videoTitle) || card.querySelector('h3')?.textContent?.trim() || '';
            const confirmMessage = titleValue ? `「${titleValue}」を削除しますか？\n視聴履歴も同時に削除されます。` : 'この動画を削除しますか？';
            const confirmed = window.confirm(confirmMessage);
            if (!confirmed) return;

            try {
                const response = await fetch(`/api/admin/training-videos/${videoId}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (!response.ok || result.status !== 'success') {
                    const errorMessage = result && result.message ? result.message : '削除に失敗しました。';
                    throw new Error(errorMessage);
                }
                window.location.reload();
            } catch (error) {
                console.error(error);
                alert(error && error.message ? error.message : '削除に失敗しました。');
            }
        });
    });
});

