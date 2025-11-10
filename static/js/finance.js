document.addEventListener('DOMContentLoaded', () => {
    const invoiceModal = document.getElementById('invoiceModal');
    const payoutModal = document.getElementById('payoutModal');
    const invoiceForm = document.getElementById('invoiceForm');
    const payoutForm = document.getElementById('payoutForm');
    const invoiceMessage = document.getElementById('invoiceFormMessage');
    const payoutMessage = document.getElementById('payoutFormMessage');

    const invoiceTitle = document.getElementById('invoice-modal-title');
    const payoutTitle = document.getElementById('payout-modal-title');

    const addInvoiceBtn = document.getElementById('addInvoiceBtn');
    const addPayoutBtn = document.getElementById('addPayoutBtn');

    let editingInvoiceId = null;
    let editingPayoutId = null;

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

    const clearInvoiceForm = () => {
        if (!invoiceForm) return;
        invoiceForm.reset();
        editingInvoiceId = null;
        if (invoiceMessage) {
            invoiceMessage.textContent = '';
            invoiceMessage.classList.remove('error');
        }
        if (invoiceTitle) {
            invoiceTitle.textContent = '請求書を追加';
        }
        const submitButton = invoiceForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.textContent = '保存する';
        }
    };

    const clearPayoutForm = () => {
        if (!payoutForm) return;
        payoutForm.reset();
        editingPayoutId = null;
        if (payoutMessage) {
            payoutMessage.textContent = '';
            payoutMessage.classList.remove('error');
        }
        if (payoutTitle) {
            payoutTitle.textContent = '支払情報を追加';
        }
        const submitButton = payoutForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.textContent = '保存する';
        }
    };

    const closeModal = (modal) => {
        toggleModal(modal, false);
        if (modal === invoiceModal) {
            clearInvoiceForm();
        } else if (modal === payoutModal) {
            clearPayoutForm();
        }
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
            if (invoiceModal?.classList.contains('open')) closeModal(invoiceModal);
            if (payoutModal?.classList.contains('open')) closeModal(payoutModal);
        }
    });

    const showMessage = (element, text, isError = false) => {
        if (!element) return;
        element.textContent = text;
        element.classList.toggle('error', isError);
    };

    const submitFinanceForm = async ({ url, method, payload, messageElement }) => {
        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                const message = result && result.message ? result.message : '保存に失敗しました。';
                throw new Error(message);
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
        const projectInput = invoiceForm.querySelector('#invoice_project_name');
        const amountInput = invoiceForm.querySelector('#invoice_amount');
        const issueInput = invoiceForm.querySelector('#invoice_issue_date');
        const statusSelect = invoiceForm.querySelector('#invoice_status');
        if (projectInput) projectInput.value = row.dataset.projectName || '';
        if (amountInput) amountInput.value = row.dataset.amount || '';
        if (issueInput) issueInput.value = row.dataset.issueDate || '';
        if (statusSelect && row.dataset.status) {
            statusSelect.value = row.dataset.status;
        }
        if (invoiceTitle) {
            invoiceTitle.textContent = '請求書を編集';
        }
        const submitButton = invoiceForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.textContent = '更新する';
        }
    };

    const populatePayoutForm = (row) => {
        if (!payoutForm || !row) return;
        const editorInput = payoutForm.querySelector('#payout_editor');
        const projectInput = payoutForm.querySelector('#payout_project_name');
        const amountInput = payoutForm.querySelector('#payout_amount');
        const statusSelect = payoutForm.querySelector('#payout_status');
        if (editorInput) editorInput.value = row.dataset.editor || '';
        if (projectInput) projectInput.value = row.dataset.projectName || '';
        if (amountInput) amountInput.value = row.dataset.amount || '';
        if (statusSelect && row.dataset.status) {
            statusSelect.value = row.dataset.status;
        }
        if (payoutTitle) {
            payoutTitle.textContent = '支払情報を編集';
        }
        const submitButton = payoutForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.textContent = '更新する';
        }
    };

    if (addInvoiceBtn) {
        addInvoiceBtn.addEventListener('click', () => {
            clearInvoiceForm();
            toggleModal(invoiceModal, true);
        });
    }

    if (addPayoutBtn) {
        addPayoutBtn.addEventListener('click', () => {
            clearPayoutForm();
            toggleModal(payoutModal, true);
        });
    }

    document.querySelectorAll('.invoice-edit-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            const row = event.currentTarget.closest('.finance-row');
            if (!row) return;
            editingInvoiceId = row.dataset.id;
            populateInvoiceForm(row);
            toggleModal(invoiceModal, true);
        });
    });

    document.querySelectorAll('.payout-edit-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            const row = event.currentTarget.closest('.finance-row');
            if (!row) return;
            editingPayoutId = row.dataset.id;
            populatePayoutForm(row);
            toggleModal(payoutModal, true);
        });
    });

    if (invoiceForm) {
        invoiceForm.addEventListener('submit', (event) => {
            event.preventDefault();
            if (invoiceMessage) {
                showMessage(invoiceMessage, '保存中...');
            }
            const formData = new FormData(invoiceForm);
            const payload = {
                project_name: (formData.get('project_name') || '').toString().trim(),
                amount: formData.get('amount'),
                issue_date: formData.get('issue_date'),
                status: formData.get('status')
            };
            if (!payload.project_name) {
                showMessage(invoiceMessage, '案件名は必須です。', true);
                return;
            }
            if (!payload.amount && payload.amount !== 0) {
                showMessage(invoiceMessage, '金額は必須です。', true);
                return;
            }
            const url = editingInvoiceId ? `/api/finance/invoices/${editingInvoiceId}` : '/api/finance/invoices';
            const method = editingInvoiceId ? 'PUT' : 'POST';
            submitFinanceForm({ url, method, payload, messageElement: invoiceMessage });
        });
    }

    if (payoutForm) {
        payoutForm.addEventListener('submit', (event) => {
            event.preventDefault();
            if (payoutMessage) {
                showMessage(payoutMessage, '保存中...');
            }
            const formData = new FormData(payoutForm);
            const payload = {
                editor: (formData.get('editor') || '').toString().trim(),
                project_name: (formData.get('project_name') || '').toString().trim(),
                amount: formData.get('amount'),
                status: formData.get('status')
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
            const url = editingPayoutId ? `/api/finance/payouts/${editingPayoutId}` : '/api/finance/payouts';
            const method = editingPayoutId ? 'PUT' : 'POST';
            submitFinanceForm({ url, method, payload, messageElement: payoutMessage });
        });
    }
});

