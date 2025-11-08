document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('adminTrainingForm');
    const message = document.getElementById('adminTrainingMessage');

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
});

