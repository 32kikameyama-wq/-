document.addEventListener('DOMContentLoaded', () => {
    const invoiceModal = document.getElementById('invoiceModal');
    const payoutModal = document.getElementById('payoutModal');
    const invoiceUploadModal = document.getElementById('invoiceUploadModal');
    const payoutUploadModal = document.getElementById('payoutUploadModal');

    const invoiceForm = document.getElementById('invoiceForm');
    const payoutForm = document.getElementById('payoutForm');
    const invoiceUploadForm = document.getElementById('invoiceUploadForm');
    const payoutUploadForm = document.getElementById('payoutUploadForm');

    const invoiceMessage = document.getElementById('invoiceFormMessage');
    const payoutMessage = document.getElementById('payoutFormMessage');
    const invoiceUploadMessage = document.getElementById('invoiceUploadFormMessage');
    const payoutUploadMessage = document.getElementById('payoutUploadFormMessage');

    const invoiceTitle = document.getElementById('invoice-modal-title');
    const payoutTitle = document.getElementById('payout-modal-title');
    const invoiceUploadTitle = document.getElementById('invoice-upload-modal-title');
    const payoutUploadTitle = document.getElementById('payout-upload-modal-title');

    const invoiceCurrentFile = document.getElementById('invoiceUploadCurrentFile');
    const payoutCurrentFile = document.getElementById('payoutUploadCurrentFile');

    const addInvoiceManualBtn = document.getElementById('addInvoiceManualBtn');
    const addInvoicePdfBtn = document.getElementById('addInvoicePdfBtn');
    const addPayoutManualBtn = document.getElementById('addPayoutManualBtn');
    const addPayoutPdfBtn = document.getElementById('addPayoutPdfBtn');

    let editingInvoiceManualId = null;
    let editingInvoiceUploadId = null;
    let editingPayoutManualId = null;
    let editingPayoutUploadId = null;

    const toggleModal = (modal, open) => {
        if (!modal) return;
        const shouldOpen = typeof open === 'boolean' ? open : !modal.classList.contains('open');
        if (shouldOpen) {
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
        } else {
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
        }
    };

    const showMessage = (element, text, isError = false) => {
        if (!element) return;
        element.textContent = text;
        element.classList.toggle('error', isError);
    };

    const resetMessage = (element) => {
        if (!element) return;
        element.textContent = '';
        element.classList.remove('error');
    };

    const clearInvoiceForm = () => {
        if (!invoiceForm) return;
        invoiceForm.reset();
        editingInvoiceManualId = null;
        resetMessage(invoiceMessage);
        if (invoiceTitle) invoiceTitle.textContent = '請求書を追加';
        const submitButton = invoiceForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '保存する';
    };

    const clearPayoutForm = () => {
        if (!payoutForm) return;
        payoutForm.reset();
        editingPayoutManualId = null;
        resetMessage(payoutMessage);
        if (payoutTitle) payoutTitle.textContent = '支払情報を追加';
        const submitButton = payoutForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '保存する';
    };

    const clearInvoiceUploadForm = () => {
        if (!invoiceUploadForm) return;
        invoiceUploadForm.reset();
        editingInvoiceUploadId = null;
        resetMessage(invoiceUploadMessage);
        if (invoiceUploadTitle) invoiceUploadTitle.textContent = '請求書PDFを取り込む';
        if (invoiceCurrentFile) invoiceCurrentFile.textContent = 'PDFファイルを選択してください。';
        const submitButton = invoiceUploadForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = 'アップロード';
    };

    const clearPayoutUploadForm = () => {
        if (!payoutUploadForm) return;
        payoutUploadForm.reset();
        editingPayoutUploadId = null;
        resetMessage(payoutUploadMessage);
        if (payoutUploadTitle) payoutUploadTitle.textContent = '支払PDFを取り込む';
        if (payoutCurrentFile) payoutCurrentFile.textContent = 'PDFファイルを選択してください。';
        const submitButton = payoutUploadForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = 'アップロード';
    };

    const closeModal = (modal) => {
        toggleModal(modal, false);
        if (modal === invoiceModal) clearInvoiceForm();
        if (modal === payoutModal) clearPayoutForm();
        if (modal === invoiceUploadModal) clearInvoiceUploadForm();
        if (modal === payoutUploadModal) clearPayoutUploadForm();
    };

    document.querySelectorAll('[data-close-target]').forEach((element) => {
        element.addEventListener('click', (event) => {
            const targetId = element.getAttribute('data-close-target');
            if (!targetId) return;
            const modal = document.getElementById(targetId);
            if (!modal) return;
            if (event.target === element || element.classList.contains('gantt-modal-close') || element.classList.contains('btn')) {
                closeModal(modal);
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            [invoiceModal, payoutModal, invoiceUploadModal, payoutUploadModal].forEach((modal) => {
                if (modal?.classList.contains('open')) closeModal(modal);
            });
        }
    });

    const submitFinanceJSON = async ({ url, method, payload, messageElement }) => {
        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                throw new Error(result?.message || '保存に失敗しました。');
            }
            showMessage(messageElement, '保存しました。ページを更新しています...');
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            console.error(error);
            showMessage(messageElement, error.message || '保存に失敗しました。', true);
        }
    };

    const submitFinanceMultipart = async ({ url, method, formData, messageElement }) => {
        try {
            const response = await fetch(url, {
                method,
                body: formData
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                throw new Error(result?.message || '保存に失敗しました。');
            }
            showMessage(messageElement, '保存しました。ページを更新しています...');
            setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            console.error(error);
            showMessage(messageElement, error.message || '保存に失敗しました。', true);
        }
    };

    const populateInvoiceForm = (row) => {
        if (!invoiceForm || !row) return;
        invoiceForm.querySelector('#invoice_project_name').value = row.dataset.projectName || '';
        invoiceForm.querySelector('#invoice_amount').value = row.dataset.amount || '';
        invoiceForm.querySelector('#invoice_issue_date').value = row.dataset.issueDate || '';
        invoiceForm.querySelector('#invoice_status').value = row.dataset.status || 'draft';
        invoiceForm.querySelector('#invoice_notes').value = row.dataset.notes || '';
        if (invoiceTitle) invoiceTitle.textContent = '請求書を編集';
        const submitButton = invoiceForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '更新する';
    };

    const populatePayoutForm = (row) => {
        if (!payoutForm || !row) return;
        payoutForm.querySelector('#payout_editor').value = row.dataset.editor || '';
        payoutForm.querySelector('#payout_project_name').value = row.dataset.projectName || '';
        payoutForm.querySelector('#payout_amount').value = row.dataset.amount || '';
        payoutForm.querySelector('#payout_status').value = row.dataset.status || 'pending';
        payoutForm.querySelector('#payout_notes').value = row.dataset.notes || '';
        if (payoutTitle) payoutTitle.textContent = '支払情報を編集';
        const submitButton = payoutForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '更新する';
    };

    const populateInvoiceUploadForm = (row) => {
        if (!invoiceUploadForm || !row) return;
        invoiceUploadForm.querySelector('#invoice_upload_project').value = row.dataset.projectName || '';
        invoiceUploadForm.querySelector('#invoice_upload_amount').value = row.dataset.amount || '';
        invoiceUploadForm.querySelector('#invoice_upload_issue_date').value = row.dataset.issueDate || '';
        invoiceUploadForm.querySelector('#invoice_upload_status').value = row.dataset.status || 'draft';
        invoiceUploadForm.querySelector('#invoice_upload_notes').value = row.dataset.notes || '';
        const fileName = row.dataset.attachmentName || '（未登録）';
        if (invoiceCurrentFile) {
            if (row.dataset.attachmentUrl) {
                invoiceCurrentFile.innerHTML = `現在のファイル: <a href="${row.dataset.attachmentUrl}" target="_blank" rel="noopener">${fileName}</a><br>差し替える場合は新しいPDFを選択してください。`;
            } else {
                invoiceCurrentFile.textContent = `現在のファイル: ${fileName}`;
            }
        }
        if (invoiceUploadTitle) invoiceUploadTitle.textContent = '請求書PDFを編集';
        const submitButton = invoiceUploadForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '更新する';
    };

    const populatePayoutUploadForm = (row) => {
        if (!payoutUploadForm || !row) return;
        payoutUploadForm.querySelector('#payout_upload_editor').value = row.dataset.editor || '';
        payoutUploadForm.querySelector('#payout_upload_project').value = row.dataset.projectName || '';
        payoutUploadForm.querySelector('#payout_upload_amount').value = row.dataset.amount || '';
        payoutUploadForm.querySelector('#payout_upload_status').value = row.dataset.status || 'pending';
        payoutUploadForm.querySelector('#payout_upload_notes').value = row.dataset.notes || '';
        const fileName = row.dataset.attachmentName || '（未登録）';
        if (payoutCurrentFile) {
            if (row.dataset.attachmentUrl) {
                payoutCurrentFile.innerHTML = `現在のファイル: <a href="${row.dataset.attachmentUrl}" target="_blank" rel="noopener">${fileName}</a><br>差し替える場合は新しいPDFを選択してください。`;
            } else {
                payoutCurrentFile.textContent = `現在のファイル: ${fileName}`;
            }
        }
        if (payoutUploadTitle) payoutUploadTitle.textContent = '支払PDFを編集';
        const submitButton = payoutUploadForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = '更新する';
    };

    if (addInvoiceManualBtn) {
        addInvoiceManualBtn.addEventListener('click', () => {
            clearInvoiceForm();
            toggleModal(invoiceModal, true);
        });
    }

    if (addInvoicePdfBtn) {
        addInvoicePdfBtn.addEventListener('click', () => {
            clearInvoiceUploadForm();
            toggleModal(invoiceUploadModal, true);
        });
    }

    if (addPayoutManualBtn) {
        addPayoutManualBtn.addEventListener('click', () => {
            clearPayoutForm();
            toggleModal(payoutModal, true);
        });
    }

    if (addPayoutPdfBtn) {
        addPayoutPdfBtn.addEventListener('click', () => {
            clearPayoutUploadForm();
            toggleModal(payoutUploadModal, true);
        });
    }

    document.querySelectorAll('.invoice-edit-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            const row = event.currentTarget.closest('.finance-row');
            if (!row) return;
            if ((row.dataset.inputSource || 'manual') === 'pdf') {
                editingInvoiceUploadId = row.dataset.id;
                populateInvoiceUploadForm(row);
                toggleModal(invoiceUploadModal, true);
            } else {
                editingInvoiceManualId = row.dataset.id;
                populateInvoiceForm(row);
                toggleModal(invoiceModal, true);
            }
        });
    });

    document.querySelectorAll('.payout-edit-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            const row = event.currentTarget.closest('.finance-row');
            if (!row) return;
            if ((row.dataset.inputSource || 'manual') === 'pdf') {
                editingPayoutUploadId = row.dataset.id;
                populatePayoutUploadForm(row);
                toggleModal(payoutUploadModal, true);
            } else {
                editingPayoutManualId = row.dataset.id;
                populatePayoutForm(row);
                toggleModal(payoutModal, true);
            }
        });
    });

    if (invoiceForm) {
        invoiceForm.addEventListener('submit', (event) => {
            event.preventDefault();
            showMessage(invoiceMessage, '保存中...');
            const formData = new FormData(invoiceForm);
            const payload = {
                project_name: (formData.get('project_name') || '').toString().trim(),
                amount: formData.get('amount'),
                issue_date: formData.get('issue_date'),
                status: formData.get('status'),
                notes: (formData.get('notes') || '').toString().trim()
            };
            if (!payload.project_name) {
                showMessage(invoiceMessage, '案件名は必須です。', true);
                return;
            }
            if (!payload.amount && payload.amount !== 0) {
                showMessage(invoiceMessage, '金額は必須です。', true);
                return;
            }
            const url = editingInvoiceManualId ? `/api/finance/invoices/${editingInvoiceManualId}` : '/api/finance/invoices';
            const method = editingInvoiceManualId ? 'PUT' : 'POST';
            submitFinanceJSON({ url, method, payload, messageElement: invoiceMessage });
        });
    }

    if (payoutForm) {
        payoutForm.addEventListener('submit', (event) => {
            event.preventDefault();
            showMessage(payoutMessage, '保存中...');
            const formData = new FormData(payoutForm);
            const payload = {
                editor: (formData.get('editor') || '').toString().trim(),
                project_name: (formData.get('project_name') || '').toString().trim(),
                amount: formData.get('amount'),
                status: formData.get('status'),
                notes: (formData.get('notes') || '').toString().trim()
            };
            if (!payload.editor) {
                showMessage(payoutMessage, '編集者名は必須です。', true);
                return;
            }
            if (!payload.project_name) {
                showMessage(payoutMessage, '案件名は必須です。', true);
                return;
            }
            if (!payload.amount && payload.amount !== 0) {
                showMessage(payoutMessage, '金額は必須です。', true);
                return;
            }
            const url = editingPayoutManualId ? `/api/finance/payouts/${editingPayoutManualId}` : '/api/finance/payouts';
            const method = editingPayoutManualId ? 'PUT' : 'POST';
            submitFinanceJSON({ url, method, payload, messageElement: payoutMessage });
        });
    }

    if (invoiceUploadForm) {
        invoiceUploadForm.addEventListener('submit', (event) => {
            event.preventDefault();
            showMessage(invoiceUploadMessage, 'アップロード中...');
            const fileInput = invoiceUploadForm.querySelector('#invoice_upload_file');
            if (!editingInvoiceUploadId && fileInput && fileInput.files.length === 0) {
                showMessage(invoiceUploadMessage, 'PDFファイルを選択してください。', true);
                return;
            }
            const formData = new FormData(invoiceUploadForm);
            formData.set('input_source', 'pdf');
            const url = editingInvoiceUploadId ? `/api/finance/invoices/${editingInvoiceUploadId}` : '/api/finance/invoices';
            const method = editingInvoiceUploadId ? 'PUT' : 'POST';
            submitFinanceMultipart({ url, method, formData, messageElement: invoiceUploadMessage });
        });
    }

    if (payoutUploadForm) {
        payoutUploadForm.addEventListener('submit', (event) => {
            event.preventDefault();
            showMessage(payoutUploadMessage, 'アップロード中...');
            const fileInput = payoutUploadForm.querySelector('#payout_upload_file');
            if (!editingPayoutUploadId && fileInput && fileInput.files.length === 0) {
                showMessage(payoutUploadMessage, 'PDFファイルを選択してください。', true);
                return;
            }
            const formData = new FormData(payoutUploadForm);
            formData.set('input_source', 'pdf');
            const url = editingPayoutUploadId ? `/api/finance/payouts/${editingPayoutUploadId}` : '/api/finance/payouts';
            const method = editingPayoutUploadId ? 'PUT' : 'POST';
            submitFinanceMultipart({ url, method, formData, messageElement: payoutUploadMessage });
        });
    }
});

