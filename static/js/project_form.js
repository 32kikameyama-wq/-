// 案件追加フォームのJavaScript

function addProject(companyId = null) {
    // モーダルまたはフォームを表示
    const form = document.createElement('div');
    form.className = 'project-form-modal';
    form.innerHTML = `
        <div class="modal-overlay" onclick="closeProjectForm()">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>新規案件を追加</h3>
                    <button class="close-btn" onclick="closeProjectForm()">×</button>
                </div>
                <form id="projectForm" class="project-form">
                    <input type="hidden" id="project_id" name="project_id" value="">
                    <input type="hidden" id="form_mode" name="form_mode" value="add">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="company_id_select">会社 *</label>
                            <select id="company_id_select" name="company_id" required>
                                <option value="">選択してください</option>
                                ${getCompanyOptions(companyId)}
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="project_name">企画タイトル *</label>
                            <input type="text" id="project_name" name="project_name" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="due_date">納期 *</label>
                            <input type="date" id="due_date" name="due_date" required>
                        </div>
                        <div class="form-group">
                            <label for="assignee">担当 *</label>
                            <input type="text" id="assignee" name="assignee" placeholder="例: (完)テスト" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="completion_length">完成尺（分）</label>
                            <input type="number" id="completion_length" name="completion_length" min="0">
                        </div>
                        <div class="form-group">
                            <label for="video_axis">区分 *</label>
                            <select id="video_axis" name="video_axis" required>
                                <option value="LONG">LONG（長尺）</option>
                                <option value="SHORT">SHORT（ショート）</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="status">ステータス</label>
                            <select id="status" name="status">
                                <option value="進行中">進行中</option>
                                <option value="レビュー中">レビュー中</option>
                                <option value="完了">完了</option>
                                <option value="計画中">計画中</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="raw_material_url">動画素材URL</label>
                            <input type="url" id="raw_material_url" name="raw_material_url" placeholder="https://drive.google.com/...">
                        </div>
                        <div class="form-group">
                            <label for="final_video_url">完成動画URL</label>
                            <input type="url" id="final_video_url" name="final_video_url" placeholder="https://drive.google.com/...">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="script_url">台本URL</label>
                            <input type="url" id="script_url" name="script_url" placeholder="https://drive.google.com/...">
                        </div>
                        <div class="form-group">
                            <label for="delivery_date">納品完了日</label>
                            <input type="date" id="delivery_date" name="delivery_date">
                        </div>
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeProjectForm()">キャンセル</button>
                        <button type="submit" class="btn btn-primary" id="submit-btn">追加</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    
    document.body.appendChild(form);
    
    // フォーム送信処理
    document.getElementById('projectForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitProjectForm();
    });
}

function closeProjectForm() {
    const modal = document.querySelector('.project-form-modal');
    if (modal) {
        modal.remove();
    }
}

function getCompanyOptions(selectedCompanyId = null) {
    // 会社一覧を取得（実際にはAPIから取得するか、グローバル変数から取得）
    const companies = window.companies || [];
    return companies.map(company => {
        const selected = selectedCompanyId && company.id == selectedCompanyId ? 'selected' : '';
        return `<option value="${company.id}" ${selected}>${company.name}</option>`;
    }).join('');
}

function showEditProjectForm(project) {
    const form = document.createElement('div');
    form.className = 'project-form-modal';
    form.innerHTML = `
        <div class="modal-overlay" onclick="closeProjectForm()">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>案件を編集</h3>
                    <button class="close-btn" onclick="closeProjectForm()">×</button>
                </div>
                <form id="projectForm" class="project-form">
                    <input type="hidden" id="project_id" name="project_id" value="${project.id}">
                    <input type="hidden" id="form_mode" name="form_mode" value="edit">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="company_id_select">会社 *</label>
                            <select id="company_id_select" name="company_id" required>
                                <option value="">選択してください</option>
                                ${getCompanyOptions(project.company_id)}
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="project_name">企画タイトル *</label>
                            <input type="text" id="project_name" name="project_name" value="${project.name || ''}" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="due_date">納期 *</label>
                            <input type="date" id="due_date" name="due_date" value="${project.due_date || ''}" required>
                        </div>
                        <div class="form-group">
                            <label for="assignee">担当 *</label>
                            <input type="text" id="assignee" name="assignee" value="${project.assignee || ''}" placeholder="例: (完)テスト" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="completion_length">完成尺（分）</label>
                            <input type="number" id="completion_length" name="completion_length" value="${project.completion_length || ''}" min="0">
                        </div>
                        <div class="form-group">
                            <label for="video_axis">区分 *</label>
                            <select id="video_axis" name="video_axis" required>
                                <option value="LONG" ${project.video_axis === 'LONG' ? 'selected' : ''}>LONG（長尺）</option>
                                <option value="SHORT" ${project.video_axis === 'SHORT' ? 'selected' : ''}>SHORT（ショート）</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="status">ステータス</label>
                            <select id="status" name="status">
                                <option value="進行中" ${project.status === '進行中' ? 'selected' : ''}>進行中</option>
                                <option value="レビュー中" ${project.status === 'レビュー中' ? 'selected' : ''}>レビュー中</option>
                                <option value="完了" ${project.status === '完了' ? 'selected' : ''}>完了</option>
                                <option value="計画中" ${project.status === '計画中' ? 'selected' : ''}>計画中</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="raw_material_url">動画素材URL</label>
                            <input type="url" id="raw_material_url" name="raw_material_url" value="${project.raw_material_url || ''}" placeholder="https://drive.google.com/...">
                        </div>
                        <div class="form-group">
                            <label for="final_video_url">完成動画URL</label>
                            <input type="url" id="final_video_url" name="final_video_url" value="${project.final_video_url || ''}" placeholder="https://drive.google.com/...">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="script_url">台本URL</label>
                            <input type="url" id="script_url" name="script_url" value="${project.script_url || ''}" placeholder="https://drive.google.com/...">
                        </div>
                        <div class="form-group">
                            <label for="delivery_date">納品完了日</label>
                            <input type="date" id="delivery_date" name="delivery_date" value="${project.delivery_date || ''}">
                        </div>
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeProjectForm()">キャンセル</button>
                        <button type="submit" class="btn btn-primary">更新</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    
    document.body.appendChild(form);
    
    // フォーム送信処理
    document.getElementById('projectForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitProjectForm();
    });
}

function submitProjectForm() {
    const form = document.getElementById('projectForm');
    const formData = new FormData(form);
    const mode = formData.get('form_mode');
    const projectId = formData.get('project_id');
    
    const data = {
        company_id: parseInt(formData.get('company_id')),
        name: formData.get('project_name'),
        due_date: formData.get('due_date'),
        assignee: formData.get('assignee'),
        completion_length: formData.get('completion_length') ? parseInt(formData.get('completion_length')) : null,
        video_axis: formData.get('video_axis') || 'LONG',
        status: formData.get('status') || '進行中',
        raw_material_url: formData.get('raw_material_url') || '',
        final_video_url: formData.get('final_video_url') || '',
        script_url: formData.get('script_url') || '',
        delivery_date: formData.get('delivery_date') || '',
        delivered: false
    };
    
    const url = mode === 'edit' ? `/api/projects/${projectId}` : '/api/projects';
    const method = mode === 'edit' ? 'PUT' : 'POST';
    
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            closeProjectForm();
            setTimeout(() => {
                location.reload();
            }, 300);
        } else {
            alert('エラー: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('案件の保存中にエラーが発生しました。');
    });
}

// 会社登録フォーム
function addCompany() {
    const form = document.createElement('div');
    form.className = 'project-form-modal';
    form.innerHTML = `
        <div class="modal-overlay" onclick="closeCompanyForm()">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>新規会社を登録</h3>
                    <button class="close-btn" onclick="closeCompanyForm()">×</button>
                </div>
                <form id="companyForm" class="project-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="company_name">会社名 *</label>
                            <input type="text" id="company_name" name="company_name" required placeholder="例: A社">
                        </div>
                        <div class="form-group">
                            <label for="company_code">会社コード *</label>
                            <input type="text" id="company_code" name="company_code" required placeholder="例: COMPANY_A" pattern="[A-Z0-9_]+">
                            <small style="color: #666; font-size: 0.8em;">英大文字、数字、アンダースコアのみ</small>
                        </div>
                    </div>
                    <div class="form-info">
                        <p style="color: #666; font-size: 0.9em; margin: 10px 0;">
                            <strong>注意:</strong> 会社を登録すると、専用の管理ページが自動的に作成されます。
                        </p>
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeCompanyForm()">キャンセル</button>
                        <button type="submit" class="btn btn-primary">登録</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    
    document.body.appendChild(form);
    
    // フォーム送信処理
    document.getElementById('companyForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitCompanyForm();
    });
}

function closeCompanyForm() {
    const modal = document.querySelector('.project-form-modal');
    if (modal && modal.querySelector('#companyForm')) {
        modal.remove();
    }
}

function submitCompanyForm() {
    const form = document.getElementById('companyForm');
    const formData = new FormData(form);
    const data = {
        company_name: formData.get('company_name'),
        company_code: formData.get('company_code')
    };
    
    // APIに送信
    fetch('/api/companies', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            alert('会社が登録されました。\n専用の管理ページが作成されました。\n\n管理ページURL: ' + result.data.management_url);
            closeCompanyForm();
            // ページをリロードして新しい会社を表示
            setTimeout(() => {
                location.reload();
            }, 500);
        } else {
            alert('エラー: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('会社登録中にエラーが発生しました。');
    });
}

