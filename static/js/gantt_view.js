(function () {
    const state = {
        allTasks: [],
        filteredTasks: [],
        taskMap: new Map(),
        selectedTaskId: null,
        dependenciesBuffer: [],
        view: (window.GANTT_CURRENT_VIEW || 'plan'),
        role: window.GANTT_USER_ROLE || 'editor',
        filters: {
            project_id: '',
            assignee: '',
            status: '',
            keyword: '',
            start_date: '',
            end_date: ''
        },
        gantt: null,
        dependencyTypes: window.GANTT_DEPENDENCY_TYPES || ['FS', 'SS', 'FF', 'SF'],
        isSaving: false
    };

    const FIELD_LABELS = {
        title: 'タスク名',
        type: '種別',
        status: 'ステータス',
        assignee: '担当者',
        due_date: '納期',
        priority: '優先度',
        progress: '進捗',
        plan_start: '計画開始',
        plan_end: '計画終了',
        actual_start: '実績開始',
        actual_end: '実績終了',
        order_index: '並び順',
        notes: 'メモ',
        project_id: '案件',
        project_name: '案件',
        dependencies: '依存関係'
    };

    const refs = {};

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        cacheRefs();
        if (!refs.container) {
            return;
        }

        populateFilterOptions(window.GANTT_FILTER_OPTIONS || {});
        populateProjectSelect(window.GANTT_FILTER_OPTIONS || {});

        state.allTasks = normalizeTasks(window.GANTT_INITIAL_DATA || []);
        syncTaskMap(state.allTasks);
        state.filteredTasks = [...state.allTasks];
        renderGantt();
        bindEvents();

        refreshTasks({ showLoading: false });
    }

    function cacheRefs() {
        refs.container = document.getElementById('gantt-container');
        refs.viewport = document.querySelector('.gantt-viewport');
        refs.emptyState = document.getElementById('gantt-empty-state');
        refs.addButton = document.getElementById('gantt-add-task-btn');
        refs.refreshButton = document.getElementById('gantt-refresh-btn');
        refs.emptyAddButton = document.getElementById('gantt-empty-add-btn');
        refs.filterProject = document.getElementById('gantt-filter-project');
        refs.filterAssignee = document.getElementById('gantt-filter-assignee');
        refs.filterStatus = document.getElementById('gantt-filter-status');
        refs.filterKeyword = document.getElementById('gantt-filter-keyword');
        refs.filterStart = document.getElementById('gantt-filter-start');
        refs.filterEnd = document.getElementById('gantt-filter-end');
        refs.filterApply = document.getElementById('gantt-filter-apply');
        refs.filterReset = document.getElementById('gantt-filter-reset');
        refs.viewToggleButtons = Array.from(document.querySelectorAll('.view-toggle-btn'));
        refs.sidePanel = document.getElementById('gantt-side-panel');
        refs.sidePanelClose = document.getElementById('gantt-panel-close');
        refs.sidePanelCancel = document.getElementById('gantt-panel-cancel');
        refs.sidePanelSave = document.getElementById('gantt-panel-save');
        refs.historyButton = document.getElementById('gantt-history-btn');
        refs.historyModal = document.getElementById('gantt-history-modal');
        refs.historyList = document.getElementById('gantt-history-list');
        refs.taskModal = document.getElementById('gantt-task-modal');
        refs.taskForm = document.getElementById('gantt-task-form');
        refs.modalProject = document.getElementById('modal-task-project');
        refs.dependenciesSelect = document.getElementById('gantt-dependencies');
        refs.dependencyType = document.getElementById('gantt-dependency-type');
        refs.applyDependency = document.getElementById('gantt-apply-dependency');
        refs.clearDependency = document.getElementById('gantt-clear-dependency');
        refs.dependencyList = document.getElementById('gantt-dependency-list');
        refs.moveUp = document.getElementById('gantt-move-up');
        refs.moveDown = document.getElementById('gantt-move-down');

        refs.detailFields = {
            title: document.getElementById('gantt-task-title'),
            project: document.getElementById('gantt-task-project'),
            status: document.getElementById('gantt-detail-status'),
            progress: document.getElementById('gantt-detail-progress'),
            assignee: document.getElementById('gantt-detail-assignee'),
            priority: document.getElementById('gantt-detail-priority'),
            planStart: document.getElementById('gantt-plan-start'),
            planEnd: document.getElementById('gantt-plan-end'),
            actualStart: document.getElementById('gantt-actual-start'),
            actualEnd: document.getElementById('gantt-actual-end'),
            notes: document.getElementById('gantt-detail-notes'),
            metaCreatedBy: document.getElementById('gantt-meta-created-by'),
            metaUpdated: document.getElementById('gantt-meta-updated')
        };
    }

    function bindEvents() {
        if (refs.addButton) refs.addButton.addEventListener('click', openTaskModal);
        if (refs.refreshButton) refs.refreshButton.addEventListener('click', () => refreshTasks({ showLoading: true }));
        if (refs.emptyAddButton) refs.emptyAddButton.addEventListener('click', openTaskModal);
        if (refs.filterApply) refs.filterApply.addEventListener('click', applyFilters);
        if (refs.filterReset) refs.filterReset.addEventListener('click', resetFilters);

        if (refs.filterKeyword) {
            refs.filterKeyword.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    applyFilters();
                }
            });
        }

        refs.viewToggleButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                refs.viewToggleButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.view = btn.dataset.view || 'plan';
                refreshTasks({ showLoading: false });
            });
        });

        if (refs.sidePanelClose) refs.sidePanelClose.addEventListener('click', closeSidePanel);
        if (refs.sidePanelCancel) refs.sidePanelCancel.addEventListener('click', closeSidePanel);
        if (refs.sidePanelSave) refs.sidePanelSave.addEventListener('click', saveSidePanel);
        if (refs.historyButton) refs.historyButton.addEventListener('click', openHistoryModal);

        document.querySelectorAll('[data-close-target]').forEach(elem => {
            elem.addEventListener('click', (event) => {
                const targetId = event.currentTarget.getAttribute('data-close-target');
                closeModalById(targetId);
            });
        });

        if (refs.taskForm) {
            refs.taskForm.addEventListener('submit', submitTaskForm);
        }

        if (refs.applyDependency) {
            refs.applyDependency.addEventListener('click', applyDependenciesUpdate);
        }
        if (refs.clearDependency) {
            refs.clearDependency.addEventListener('click', clearSelectedDependencies);
        }

        if (refs.moveUp) {
            refs.moveUp.addEventListener('click', () => moveTaskOrder('up'));
        }
        if (refs.moveDown) {
            refs.moveDown.addEventListener('click', () => moveTaskOrder('down'));
        }
    }

    function populateFilterOptions(options) {
        if (!options) options = {};
        const projects = options.projects || [];
        const assignees = options.assignees || [];
        const statuses = options.statuses || [];

        populateSelect(refs.filterProject, projects, { valueKey: 'id', labelKey: 'name' });
        populateSelect(refs.filterAssignee, assignees.map(a => ({ value: a, label: a })));
        populateSelect(refs.filterStatus, statuses.map(s => ({ value: s, label: s })));
    }

    function populateProjectSelect(options) {
        if (!refs.modalProject) return;
        const projects = (options.projects || []).map(p => ({ value: p.id, label: p.name }));
        populateSelect(refs.modalProject, projects);
    }

    function populateSelect(selectElem, items, config = {}) {
        if (!selectElem) return;
        const { valueKey = 'value', labelKey = 'label' } = config;
        const currentValue = selectElem.value;

        selectElem.innerHTML = '';

        if (!selectElem.multiple) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = (selectElem === refs.modalProject) ? '選択してください' : 'すべて';
            selectElem.appendChild(opt);
        }

        items.forEach(item => {
            if (item == null) return;
            const option = document.createElement('option');
            option.value = String(item[valueKey]);
            option.textContent = item[labelKey] || item[valueKey];
            selectElem.appendChild(option);
        });

        if (currentValue !== undefined && currentValue !== null) {
            selectElem.value = currentValue;
        }
    }

    function normalizeTasks(tasks) {
        return tasks.map(normalizeTask);
    }

    function normalizeTask(task) {
        const clone = { ...task };
        clone.id = Number(clone.id);
        clone.progress = Number(clone.progress || 0);
        clone.order_index = clone.order_index != null ? Number(clone.order_index) : clone.id;
        clone.dependencies = (clone.dependencies || []).map(dep => ({
            task_id: Number(dep.task_id),
            type: (dep.type || 'FS').toUpperCase()
        }));
        clone.plan_start = normalizeDateString(clone.plan_start);
        clone.plan_end = normalizeDateString(clone.plan_end);
        clone.actual_start = normalizeDateString(clone.actual_start);
        clone.actual_end = normalizeDateString(clone.actual_end);
        clone.due_date = normalizeDateString(clone.due_date);
        return clone;
    }

    function normalizeDateString(value) {
        if (!value) return '';
        if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
            return value;
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '';
        }
        return date.toISOString().slice(0, 10);
    }

    function syncTaskMap(tasks) {
        state.taskMap.clear();
        tasks.forEach(task => {
            state.taskMap.set(task.id, task);
        });
    }

    function renderGantt() {
        if (!refs.container) return;

        const tasks = state.filteredTasks.length ? state.filteredTasks : state.allTasks;
        if (!tasks.length) {
            refs.container.innerHTML = '';
            if (refs.emptyState) {
                refs.emptyState.hidden = false;
            }
            refs.container.style.visibility = 'hidden';
            if (refs.viewport) {
                refs.viewport.scrollLeft = 0;
            }
            return;
        }

        if (refs.container.style.visibility !== 'visible') {
            refs.container.style.visibility = 'visible';
        }

        if (refs.emptyState) {
            refs.emptyState.hidden = true;
        }

        if (refs.viewport) {
            refs.viewport.scrollLeft = 0;
        }

        const data = tasks.map(task => convertToGanttItem(task));
        refs.container.innerHTML = '';

        state.gantt = new Gantt(refs.container, data, {
            view_mode: 'Day',
            date_format: 'YYYY-MM-DD',
            custom_popup_html: (task) => buildTooltip(task),
            language: 'ja',
            on_click: (task) => openSidePanel(task.id),
            on_date_change: (task, start, end) => handleDateChange(task, start, end),
            on_progress_change: (task, progress) => handleProgressChange(task, progress)
        });

        if (refs.viewport) {
            refs.viewport.scrollLeft = 0;
        }

        applyBarColors();
    }

    function convertToGanttItem(task) {
        const usePlan = state.view === 'plan';
        const start = usePlan ? (task.plan_start || task.plan_end || task.actual_start || task.actual_end || task.due_date) : (task.actual_start || task.plan_start || task.plan_end || task.due_date);
        const end = usePlan ? (task.plan_end || task.plan_start || task.due_date || start) : (task.actual_end || task.actual_start || task.plan_end || task.plan_start || start);
        const safeStart = start || formatDate(new Date());
        const safeEnd = end || safeStart;
        const statusClass = (task.status || '未着手').replace(/\s/g, '');
        const overdue = usePlan && safeEnd < formatDate(new Date()) && task.status !== '完了';

        return {
            id: String(task.id),
            name: `${task.name || task.title} ${task.assignee ? `(${task.assignee})` : ''}`.trim(),
            start: safeStart,
            end: safeEnd,
            progress: Number(task.progress || 0),
            dependencies: task.dependencies_string || task.dependencies?.map(dep => dep.task_id).join(',') || '',
            custom_class: `status-${statusClass}${overdue ? ' is-overdue' : ''}`,
            data: {
                taskId: task.id,
                status: task.status,
                assignee: task.assignee,
                project: task.project_name,
                company: task.company_name,
                priority: task.priority,
                color: task.color
            }
        };
    }

    function buildTooltip(task) {
        const baseTask = state.taskMap.get(Number(task.id)) || {};
        const status = baseTask.status || '-';
        const assignee = baseTask.assignee || '未割当';
        const project = baseTask.project_name || '-';
        const company = baseTask.company_name || '-';
        const colorSwatch = baseTask.color ? `<span class="tooltip-color" style="background:${baseTask.color};"></span>` : '';
        return `
            <div class="gantt-tooltip">
                <h3>${task.name}</h3>
                <p><strong>会社:</strong> ${company} ${colorSwatch}</p>
                <p><strong>案件:</strong> ${project}</p>
                <p><strong>担当:</strong> ${assignee}</p>
                <p><strong>期間:</strong> ${task.start} 〜 ${task.end}</p>
                <p><strong>ステータス:</strong> ${status}</p>
                <p><strong>進捗:</strong> ${task.progress}%</p>
            </div>
        `;
    }

    function handleDateChange(task, start, end) {
        const taskId = Number(task.id);
        const payload = {};
        const startDate = formatDate(start);
        const endDate = formatDate(end);

        if (state.view === 'plan') {
            payload.plan_start = startDate;
            payload.plan_end = endDate;
        } else {
            payload.actual_start = startDate;
            payload.actual_end = endDate;
        }

        updateTask(taskId, payload, { silent: true })
            .then(() => refreshTasks({ showLoading: false, keepSelection: true }))
            .catch(() => {
                // revert to previous value by reloading tasks
                refreshTasks({ showLoading: false, keepSelection: true });
            });
    }

    function handleProgressChange(task, progress) {
        const taskId = Number(task.id);
        updateTask(taskId, { progress: Math.round(progress) }, { silent: true })
            .then(() => refreshTasks({ showLoading: false, keepSelection: true }))
            .catch(() => refreshTasks({ showLoading: false, keepSelection: true }));
    }

    function applyFilters() {
        state.filters = {
            project_id: refs.filterProject ? refs.filterProject.value : '',
            assignee: refs.filterAssignee ? refs.filterAssignee.value : '',
            status: refs.filterStatus ? refs.filterStatus.value : '',
            keyword: refs.filterKeyword ? refs.filterKeyword.value.trim() : '',
            start_date: refs.filterStart ? refs.filterStart.value : '',
            end_date: refs.filterEnd ? refs.filterEnd.value : ''
        };
        refreshTasks({ showLoading: true });
    }

    function resetFilters() {
        Object.keys(state.filters).forEach(key => state.filters[key] = '');
        if (refs.filterProject) refs.filterProject.value = '';
        if (refs.filterAssignee) refs.filterAssignee.value = '';
        if (refs.filterStatus) refs.filterStatus.value = '';
        if (refs.filterKeyword) refs.filterKeyword.value = '';
        if (refs.filterStart) refs.filterStart.value = '';
        if (refs.filterEnd) refs.filterEnd.value = '';
        refreshTasks({ showLoading: true });
    }

    function refreshTasks(options = {}) {
        const {
            showLoading = false,
            keepSelection = false
        } = options;

        const params = new URLSearchParams();
        params.append('view', state.view);
        Object.entries(state.filters).forEach(([key, value]) => {
            if (value) params.append(key, value);
        });
        if (state.role === 'admin' || state.role === 'editor') {
            params.append('include_history', '0');
        }

        if (showLoading) {
            refs.container?.classList.add('loading');
            refs.viewport?.classList.add('is-loading');
        }

        fetch(`/api/gantt/tasks?${params.toString()}`)
            .then(res => res.json())
            .then(json => {
                if (json.status !== 'success') {
                    throw new Error(json.message || 'ガント情報の取得に失敗しました');
                }
                const data = normalizeTasks(json.data || []);
                state.filteredTasks = data;
                syncTaskMap([...state.taskMap.values(), ...data]);

                if (json.meta && json.meta.all_tasks) {
                    state.allTasks = normalizeTasks(json.meta.all_tasks);
                    syncTaskMap(state.allTasks);
                    // update project select with latest list
                    populateFilterOptions(json.meta.filters || {});
                    populateProjectSelect(json.meta.filters || {});
                }

                renderGantt();

                if (keepSelection && state.selectedTaskId) {
                    openSidePanel(state.selectedTaskId);
                } else if (!keepSelection) {
                    closeSidePanel();
                }
            })
            .catch(error => {
                console.error(error);
                alert(error.message || 'ガント情報の取得に失敗しました');
            })
            .finally(() => {
                refs.container?.classList.remove('loading');
                refs.viewport?.classList.remove('is-loading');
                applyBarColors();
            });
    }

    function openSidePanel(taskId) {
        const numericId = Number(taskId);
        const task = state.allTasks.find(t => t.id === numericId);
        if (!task || !refs.sidePanel) return;

        state.selectedTaskId = numericId;
        state.dependenciesBuffer = task.dependencies ? task.dependencies.map(dep => ({ ...dep })) : [];

        refs.detailFields.title.textContent = task.name || task.title || '(名称未設定)';
        refs.detailFields.project.textContent = `案件: ${task.project_name || '-'}`;

        if (refs.detailFields.status) refs.detailFields.status.value = task.status || '未着手';
        if (refs.detailFields.progress) refs.detailFields.progress.value = task.progress || 0;
        if (refs.detailFields.assignee) refs.detailFields.assignee.value = task.assignee || '';
        if (refs.detailFields.priority) refs.detailFields.priority.value = task.priority || '中';
        if (refs.detailFields.planStart) refs.detailFields.planStart.value = task.plan_start || '';
        if (refs.detailFields.planEnd) refs.detailFields.planEnd.value = task.plan_end || '';
        if (refs.detailFields.actualStart) refs.detailFields.actualStart.value = task.actual_start || '';
        if (refs.detailFields.actualEnd) refs.detailFields.actualEnd.value = task.actual_end || '';
        if (refs.detailFields.notes) refs.detailFields.notes.value = task.notes || '';
        if (refs.detailFields.metaCreatedBy) refs.detailFields.metaCreatedBy.textContent = task.created_by || '-';
        if (refs.detailFields.metaUpdated) refs.detailFields.metaUpdated.textContent = task.updated_at ? `${task.updated_at} / ${task.updated_by || '-'}` : '-';

        populateDependencySelectOptions(task);
        updateDependencyPreview();
        updateReorderAvailability();

        refs.sidePanel.classList.add('open');
    }

    function closeSidePanel() {
        if (!refs.sidePanel) return;
        refs.sidePanel.classList.remove('open');
        state.selectedTaskId = null;
        state.dependenciesBuffer = [];
    }

    function populateDependencySelectOptions(currentTask) {
        if (!refs.dependenciesSelect) return;
        const options = state.allTasks
            .filter(task => task.id !== currentTask.id)
            .sort((a, b) => (a.order_index || a.id) - (b.order_index || b.id));

        refs.dependenciesSelect.innerHTML = '';
        options.forEach(task => {
            const option = document.createElement('option');
            option.value = String(task.id);
            option.textContent = `[${task.project_name || '-'}] ${task.name || task.title}`;
            if (state.dependenciesBuffer.some(dep => dep.task_id === task.id)) {
                option.selected = true;
            }
            refs.dependenciesSelect.appendChild(option);
        });

        if (refs.dependencyType) {
            const firstDep = state.dependenciesBuffer[0];
            refs.dependencyType.value = firstDep ? firstDep.type : 'FS';
        }
    }

    function updateDependencyPreview() {
        if (!refs.dependencyList) return;
        refs.dependencyList.innerHTML = '';
        if (!state.dependenciesBuffer.length) {
            const empty = document.createElement('li');
            empty.textContent = '依存関係は設定されていません';
            empty.classList.add('empty');
            refs.dependencyList.appendChild(empty);
            return;
        }

        state.dependenciesBuffer.forEach(dep => {
            const task = state.taskMap.get(dep.task_id);
            const item = document.createElement('li');
            item.textContent = `${dep.type}: ${task ? task.name || task.title : `ID:${dep.task_id}`}`;
            refs.dependencyList.appendChild(item);
        });
    }

    function applyDependenciesUpdate() {
        if (!refs.dependenciesSelect) return;
        const selectedIds = Array.from(refs.dependenciesSelect.selectedOptions).map(opt => Number(opt.value));
        const depType = refs.dependencyType ? (refs.dependencyType.value || 'FS') : 'FS';
        selectedIds.forEach(id => {
            const existing = state.dependenciesBuffer.find(dep => dep.task_id === id);
            if (existing) {
                existing.type = depType;
            } else {
                state.dependenciesBuffer.push({ task_id: id, type: depType });
            }
        });
        updateDependencyPreview();
    }

    function clearSelectedDependencies() {
        if (!refs.dependenciesSelect) return;
        const selectedIds = Array.from(refs.dependenciesSelect.selectedOptions).map(opt => Number(opt.value));
        state.dependenciesBuffer = state.dependenciesBuffer.filter(dep => !selectedIds.includes(dep.task_id));
        Array.from(refs.dependenciesSelect.options).forEach(option => {
            if (selectedIds.includes(Number(option.value))) {
                option.selected = false;
            }
        });
        updateDependencyPreview();
    }

    function saveSidePanel() {
        if (!state.selectedTaskId || state.isSaving) return;
        const payload = {
            status: refs.detailFields.status?.value || '未着手',
            progress: refs.detailFields.progress?.value || 0,
            assignee: refs.detailFields.assignee?.value || '',
            priority: refs.detailFields.priority?.value || '中',
            plan_start: refs.detailFields.planStart?.value || '',
            plan_end: refs.detailFields.planEnd?.value || '',
            actual_start: refs.detailFields.actualStart?.value || '',
            actual_end: refs.detailFields.actualEnd?.value || '',
            notes: refs.detailFields.notes?.value || '',
            dependencies: state.dependenciesBuffer
        };

        state.isSaving = true;
        refs.sidePanel?.classList.add('saving');

        updateTask(state.selectedTaskId, payload, { silent: false })
            .then(() => {
                refreshTasks({ showLoading: false, keepSelection: true });
            })
            .finally(() => {
                state.isSaving = false;
                refs.sidePanel?.classList.remove('saving');
            });
    }

    function updateTask(taskId, payload, options = {}) {
        const { silent = false } = options;
        return fetch(`/api/tasks/${taskId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(res => res.json())
            .then(json => {
                if (json.status !== 'success') {
                    throw new Error(json.message || 'タスク更新に失敗しました');
                }
                const updated = normalizeTask(json.data);
                const indexAll = state.allTasks.findIndex(task => task.id === updated.id);
                if (indexAll !== -1) {
                    state.allTasks[indexAll] = updated;
                } else {
                    state.allTasks.push(updated);
                }
                const indexFiltered = state.filteredTasks.findIndex(task => task.id === updated.id);
                if (indexFiltered !== -1) {
                    state.filteredTasks[indexFiltered] = updated;
                }
                syncTaskMap(state.allTasks);
                if (!silent) {
                    alert('タスクを更新しました');
                }
                return updated;
            })
            .catch(error => {
                console.error(error);
                if (!silent) {
                    alert(error.message || 'タスク更新中にエラーが発生しました');
                } else {
                    throw error;
                }
            });
    }

    function openHistoryModal() {
        if (!state.selectedTaskId || !refs.historyModal) return;
        fetch(`/api/gantt/tasks/${state.selectedTaskId}/history`)
            .then(res => res.json())
            .then(json => {
                if (json.status !== 'success') {
                    throw new Error(json.message || '履歴の取得に失敗しました');
                }
                renderHistoryList(json.data || []);
                refs.historyModal.classList.add('open');
            })
            .catch(error => {
                console.error(error);
                alert(error.message || '履歴の取得に失敗しました');
            });
    }

    function renderHistoryList(historyItems) {
        if (!refs.historyList) return;
        refs.historyList.innerHTML = '';
        if (!historyItems.length) {
            const item = document.createElement('li');
            item.textContent = '変更履歴はまだありません';
            refs.historyList.appendChild(item);
            return;
        }
        historyItems.forEach(entry => {
            const li = document.createElement('li');
            const label = FIELD_LABELS[entry.field] || entry.field;
            const oldValue = formatHistoryValue(entry.old, entry.field);
            const newValue = formatHistoryValue(entry.new, entry.field);
            li.innerHTML = `
                <div class="history-entry">
                    <div class="history-entry-header">
                        <span class="history-entry-label">${label}</span>
                        <span class="history-entry-meta">${entry.timestamp} / ${entry.actor || '-'}</span>
                    </div>
                    <div class="history-entry-body">
                        <span class="history-entry-old">${oldValue}</span>
                        <span class="history-entry-arrow">→</span>
                        <span class="history-entry-new">${newValue}</span>
                    </div>
                </div>
            `;
            refs.historyList.appendChild(li);
        });
    }

    function formatHistoryValue(value, field) {
        if (value === null || value === undefined || value === '') {
            return '(未設定)';
        }
        if (field === 'dependencies') {
            try {
                return (value || [])
                    .map(dep => {
                        const task = state.taskMap.get(Number(dep.task_id));
                        return `${dep.type}:${task ? task.name || task.title : dep.task_id}`;
                    })
                    .join(', ') || '(なし)';
            } catch (error) {
                return JSON.stringify(value);
            }
        }
        if (typeof value === 'object') {
            return JSON.stringify(value);
        }
        return String(value);
    }

    function closeModalById(id) {
        if (!id) return;
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.remove('open');
        }
    }

    function openTaskModal() {
        if (!refs.taskModal || !refs.modalProject) return;
        refs.taskForm.reset();
        refs.modalProject.focus();
        refs.taskModal.classList.add('open');
    }

    function submitTaskForm(event) {
        event.preventDefault();
        const formData = new FormData(refs.taskForm);
        const payload = {};
        formData.forEach((value, key) => {
            payload[key] = value;
        });
        payload.progress = Number(payload.progress || 0);

        fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(res => res.json())
            .then(json => {
                if (json.status !== 'success') {
                    throw new Error(json.message || 'タスクの作成に失敗しました');
                }
                alert('タスクを追加しました');
                closeModalById('gantt-task-modal');
                refreshTasks({ showLoading: true });
            })
            .catch(error => {
                console.error(error);
                alert(error.message || 'タスクの作成に失敗しました');
            });
    }

    function moveTaskOrder(direction) {
        if (!state.selectedTaskId) return;
        const sorted = [...state.allTasks].sort((a, b) => (a.order_index || a.id) - (b.order_index || b.id));
        const currentIndex = sorted.findIndex(task => task.id === state.selectedTaskId);
        if (currentIndex === -1) return;

        const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
        if (targetIndex < 0 || targetIndex >= sorted.length) return;

        const updatedOrder = [...sorted];
        const [removed] = updatedOrder.splice(currentIndex, 1);
        updatedOrder.splice(targetIndex, 0, removed);
        const orderPayload = updatedOrder.map(task => task.id);

        fetch('/api/gantt/tasks/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: orderPayload })
        })
            .then(res => res.json())
            .then(json => {
                if (json.status !== 'success') {
                    throw new Error(json.message || '並び順の更新に失敗しました');
                }
                // update local order indexes
                updatedOrder.forEach((task, index) => {
                    task.order_index = index + 1;
                });
                state.allTasks = updatedOrder;
                syncTaskMap(state.allTasks);
                refreshTasks({ showLoading: false, keepSelection: true });
            })
            .catch(error => {
                console.error(error);
                alert(error.message || '並び順を更新できませんでした');
            });
    }

    function updateReorderAvailability() {
        if (!state.selectedTaskId) return;
        const sorted = [...state.allTasks].sort((a, b) => (a.order_index || a.id) - (b.order_index || b.id));
        const index = sorted.findIndex(task => task.id === state.selectedTaskId);
        if (refs.moveUp) refs.moveUp.disabled = index <= 0;
        if (refs.moveDown) refs.moveDown.disabled = index === -1 || index >= sorted.length - 1;
    }

    function formatDate(date) {
        if (!date) return '';
        const d = (date instanceof Date) ? date : new Date(date);
        if (Number.isNaN(d.getTime())) {
            return '';
        }
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function applyBarColors() {
        if (!state.gantt || !state.gantt.tasks) return;
        state.gantt.tasks.forEach(taskObj => {
            const rawTask = taskObj.task || taskObj._task || {};
            const data = rawTask.data || {};
            const color = rawTask.color || data.color;
            if (color && taskObj.$bar) {
                taskObj.$bar.setAttribute('fill', color);
                taskObj.$bar.setAttribute('stroke', color);
                taskObj.$bar.setAttribute('opacity', 0.95);
            }
        });
    }
})();

