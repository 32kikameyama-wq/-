from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    url_for,
    redirect,
    session,
    g,
    abort
)
from flask_cors import CORS
import os
from datetime import datetime, timedelta
import copy
import pytz
import csv
import io
import re
import json
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

load_dotenv()

app = Flask(__name__)
CORS(app)

# 静的ファイルとテンプレートのパスを設定
app.config['STATIC_FOLDER'] = 'static'
app.config['TEMPLATES_FOLDER'] = 'templates'
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')


raw_database_url = os.environ['DATABASE_URL']
parsed_url = urlparse(raw_database_url)
query = parse_qs(parsed_url.query)
if 'sslmode' not in query:
    query['sslmode'] = ['require']
parsed_url = parsed_url._replace(query=urlencode(query, doseq=True))
DATABASE_URL = urlunparse(parsed_url)

masked_netloc = parsed_url.netloc
if parsed_url.password:
    masked_netloc = masked_netloc.replace(parsed_url.password, '****')
print(f"[startup] Using DATABASE_URL host={parsed_url.hostname} port={parsed_url.port} params={parsed_url.query}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


ROLE_LABELS = {
    'admin': '管理者',
    'editor': '編集者',
    'client': 'クライアント',
    'viewer': '閲覧'
}


EDITOR_SHARED_SETTINGS = {}


def fetch_one(query: str, **params):
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        row = result.mappings().first()
        return dict(row) if row else None


def fetch_all(query: str, **params):
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row) for row in result.mappings().all()]


def execute(query: str, **params):
    with engine.begin() as conn:
        conn.execute(text(query), params)


def ensure_tables():
    statements = [
        """
        create schema if not exists app;
        """,
        """
        create table if not exists app.users (
            id serial primary key,
            name varchar(255) not null,
            email varchar(255) not null unique,
            password_hash varchar(255) not null,
            role varchar(50) not null default 'editor',
            active boolean not null default true,
            created_at timestamp default now()
        );
        """,
        """
        create table if not exists app.editor_workspaces (
            id serial primary key,
            user_id integer not null references app.users(id),
            display_name varchar(255) not null,
            description text,
            quick_links jsonb default '[]'::jsonb,
            pinned_notices jsonb default '[]'::jsonb,
            created_at timestamp default now(),
            updated_at timestamp default now()
        );
        """,
        """
        create table if not exists app.editor_shared_settings (
            id serial primary key,
            description text,
            show_quick_links boolean default true,
            show_pinned_notices boolean default true,
            quick_links jsonb default '[]'::jsonb,
            pinned_notices jsonb default '[]'::jsonb,
            updated_at timestamp default now()
        );
        """,
        """
        create unique index if not exists idx_editor_workspaces_user
        on app.editor_workspaces(user_id);
        """
    ]
    for statement in statements:
        execute(statement)


def load_editor_shared_settings():
    global EDITOR_SHARED_SETTINGS
    row = fetch_one("select * from app.editor_shared_settings order by id limit 1")
    if not row:
        default_links = [
            {'label': '担当案件一覧', 'url': '/editor/projects', 'description': '担当案件の全体一覧'},
            {'label': 'タスクボード', 'url': '/tasks', 'description': '自分のタスクを素早く確認'},
            {'label': '素材ライブラリ', 'url': '/editor/assets', 'description': '案件別素材を確認'},
            {'label': '案件ボード', 'url': '/editor/board', 'description': '進捗を俯瞰'}
        ]
        default_notices = [
            {
                'title': 'スタートガイド',
                'body': '本ページは編集者登録と同時に自動作成される共有テンプレートです。必要に応じて担当者別にウィジェットを追加してください。',
                'updated_at': datetime.now().strftime('%Y-%m-%d')
            }
        ]
        execute(
            """
            insert into app.editor_shared_settings (
                description, show_quick_links, show_pinned_notices,
                quick_links, pinned_notices, updated_at
            ) values (:description, :show_quick_links, :show_pinned_notices, :quick_links, :pinned_notices, :updated_at)
            """,
            description='管理者が用意した共有パネル。担当案件やタスクと合わせて活用できます。',
            show_quick_links=True,
            show_pinned_notices=True,
            quick_links=json.dumps(default_links),
            pinned_notices=json.dumps(default_notices),
            updated_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        row = fetch_one("select * from app.editor_shared_settings order by id limit 1")

    EDITOR_SHARED_SETTINGS = {
        'id': row['id'],
        'description': row['description'] or '',
        'show_quick_links': row['show_quick_links'],
        'show_pinned_notices': row['show_pinned_notices'],
        'quick_links': row['quick_links'] if isinstance(row['quick_links'], list) else json.loads(row['quick_links'] or '[]'),
        'pinned_notices': row['pinned_notices'] if isinstance(row['pinned_notices'], list) else json.loads(row['pinned_notices'] or '[]'),
        'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M') if row['updated_at'] else None
    }


def build_base_editor_workspace():
    return {
        'display_name': '編集者共有ページ',
        'description': EDITOR_SHARED_SETTINGS.get('description', ''),
        'quick_links': copy.deepcopy(EDITOR_SHARED_SETTINGS.get('quick_links', [])),
        'pinned_notices': copy.deepcopy(EDITOR_SHARED_SETTINGS.get('pinned_notices', [])),
        'workspace_preferences': {
            'show_quick_links': EDITOR_SHARED_SETTINGS.get('show_quick_links', True),
            'show_pinned_notices': EDITOR_SHARED_SETTINGS.get('show_pinned_notices', True)
        },
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'last_updated': EDITOR_SHARED_SETTINGS.get('updated_at')
    }


def apply_shared_settings_to_workspace(workspace):
    workspace['description'] = EDITOR_SHARED_SETTINGS.get('description', '')
    workspace['quick_links'] = copy.deepcopy(EDITOR_SHARED_SETTINGS.get('quick_links', []))
    workspace['pinned_notices'] = copy.deepcopy(EDITOR_SHARED_SETTINGS.get('pinned_notices', []))
    workspace.setdefault('workspace_preferences', {})
    workspace['workspace_preferences']['show_quick_links'] = EDITOR_SHARED_SETTINGS.get('show_quick_links', True)
    workspace['workspace_preferences']['show_pinned_notices'] = EDITOR_SHARED_SETTINGS.get('show_pinned_notices', True)
    workspace['last_updated'] = EDITOR_SHARED_SETTINGS.get('updated_at')


def get_user_by_email(email: str):
    if not email:
        return None
    return fetch_one("select * from app.users where lower(email)=lower(:email)", email=email.strip())


def get_user_by_id(user_id: int):
    if not user_id:
        return None
    return fetch_one("select * from app.users where id=:id", id=user_id)


def list_users():
    return fetch_all("select * from app.users order by id")


def create_user(name, email, role, password_hash, active):
    execute(
        """
        insert into app.users (name, email, password_hash, role, active)
        values (:name, :email, :password_hash, :role, :active)
        """,
        name=name,
        email=email,
        password_hash=password_hash,
        role=role,
        active=active
    )
    return get_user_by_email(email)


def create_editor_workspace_for_user(user):
    workspace = build_base_editor_workspace()
    execute(
        """
        insert into app.editor_workspaces (
            user_id, display_name, description,
            quick_links, pinned_notices, created_at, updated_at
        ) values (
            :user_id, :display_name, :description,
            :quick_links, :pinned_notices, :created_at, :updated_at
        )
        on conflict (user_id) do update set
            display_name=excluded.display_name,
            description=excluded.description,
            quick_links=excluded.quick_links,
            pinned_notices=excluded.pinned_notices,
            updated_at=excluded.updated_at
        """,
        user_id=user['id'],
        display_name=f"{user['name']}さんの共有ページ",
        description=workspace['description'],
        quick_links=json.dumps(workspace['quick_links']),
        pinned_notices=json.dumps(workspace['pinned_notices']),
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        updated_at=datetime.now().strftime('%Y-%m-%d %H:%M')
    )
    return get_editor_workspace_from_db(user['id'])


def get_editor_workspace_from_db(user_id):
    row = fetch_one("select * from app.editor_workspaces where user_id=:user_id", user_id=user_id)
    if not row:
        return None
    workspace = {
        'id': row['id'],
        'user_id': row['user_id'],
        'display_name': row['display_name'],
        'description': row['description'] or '',
        'quick_links': row['quick_links'] if isinstance(row['quick_links'], list) else json.loads(row['quick_links'] or '[]'),
        'pinned_notices': row['pinned_notices'] if isinstance(row['pinned_notices'], list) else json.loads(row['pinned_notices'] or '[]'),
        'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M') if row['created_at'] else None,
        'last_updated': row['updated_at'].strftime('%Y-%m-%d %H:%M') if row['updated_at'] else None,
        'workspace_preferences': {
            'show_quick_links': EDITOR_SHARED_SETTINGS.get('show_quick_links', True),
            'show_pinned_notices': EDITOR_SHARED_SETTINGS.get('show_pinned_notices', True)
        }
    }
    apply_shared_settings_to_workspace(workspace)
    return workspace


def get_editor_workspace_for_user(user):
    if not user:
        workspace = build_base_editor_workspace()
        workspace['display_name'] = '編集者共有ページ（ゲスト）'
        return workspace
    workspace = get_editor_workspace_from_db(user['id'])
    if workspace:
        return workspace
    if user.get('role') == 'editor':
        return create_editor_workspace_for_user(user)
    workspace = build_base_editor_workspace()
    workspace['display_name'] = '編集者共有ページ（プレビュー）'
    workspace['owner_name'] = user['name']
    return workspace


def ensure_default_users():
    admin = get_user_by_email('admin@example.com')
    if not admin:
        admin = create_user(
            name='システム管理者',
            email='admin@example.com',
            role='admin',
            password_hash=generate_password_hash('adminpass'),
            active=True
        )

    editor = get_user_by_email('editor@example.com')
    if not editor:
        editor = create_user(
            name='テスト編集者',
            email='editor@example.com',
            role='editor',
            password_hash=generate_password_hash('editorpass'),
            active=True
        )

    if editor:
        create_editor_workspace_for_user(editor)


ensure_tables()
load_editor_shared_settings()
ensure_default_users()

# 認証/認可ユーティリティ


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        current_user = getattr(g, 'current_user', None)
        if not current_user:
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for('login', next=next_url))
        if not current_user.get('active', True):
            session.pop('user_id', None)
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapped_view


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            current_user = getattr(g, 'current_user', None)
            if not current_user:
                return redirect(url_for('login', next=request.path))
            if current_user.get('role') not in roles:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator


@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id) if user_id else None
    if user and not user.get('active', True):
        session.pop('user_id', None)
        user = None
    g.current_user = user


@app.before_request
def enforce_authentication():
    public_endpoints = {'login', 'static'}

    endpoint = request.endpoint
    if endpoint is None:
        return

    endpoint_root = endpoint.split('.')[-1]
    if endpoint_root in public_endpoints:
        return

    if endpoint.startswith('static'):
        return

    current_user = getattr(g, 'current_user', None)
    if not current_user:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for('login', next=next_url))


@app.context_processor
def inject_current_user():
    current_user = getattr(g, 'current_user', None)
    role_label = None
    if current_user:
        role_label = ROLE_LABELS.get(current_user.get('role'), 'ユーザー')
    return {
        'current_user': current_user,
        'current_user_role_label': role_label
    }

# サンプルデータ（システム確認用）
# 会社ごとに管理する構造

SAMPLE_COMPANIES = [
    {
        'id': 1,
        'name': 'A社',
        'code': 'COMPANY_A',
        'projects': [
            {
                'id': 1,
                'name': '監査',
                'status': '進行中',
                'due_date': '2025-04-10',
                'assignee': '(完)テスト',
                'completion_length': 5,
                'video_axis': 'LONG',
                'delivered': True,
                'delivery_date': '2025-04-08',
                'progress': 100
            },
            {
                'id': 2,
                'name': '構造',
                'status': '進行中',
                'due_date': '2025-04-10',
                'assignee': '(完)テスト',
                'completion_length': 8,
                'video_axis': 'LONG',
                'delivered': True,
                'delivery_date': '2025-04-09',
                'progress': 100
            },
            {
                'id': 3,
                'name': '工法',
                'status': '進行中',
                'due_date': '2025-04-10',
                'assignee': '(未)テスト',
                'completion_length': 6,
                'video_axis': 'SHORT',
                'delivered': False,
                'delivery_date': '',
                'progress': 70
            }
        ]
    },
    {
        'id': 2,
        'name': 'B社',
        'code': 'COMPANY_B',
        'projects': [
            {
                'id': 4,
                'name': '商品プロモーション動画',
                'status': '進行中',
                'due_date': '2025-04-15',
                'assignee': '(完)テスト',
                'completion_length': 7,
                'video_axis': 'LONG',
                'delivered': True,
                'delivery_date': '2025-04-14',
                'progress': 100
            },
            {
                'id': 5,
                'name': '企業紹介動画',
                'status': 'レビュー中',
                'due_date': '2025-04-20',
                'assignee': '(完)テスト',
                'completion_length': 10,
                'video_axis': 'LONG',
                'delivered': False,
                'delivery_date': '',
                'progress': 85
            }
        ]
    },
    {
        'id': 3,
        'name': 'C社',
        'code': 'COMPANY_C',
        'projects': [
            {
                'id': 6,
                'name': 'SNS用ショート動画',
                'status': '完了',
                'due_date': '2025-03-20',
                'assignee': '(完)テスト',
                'completion_length': 1,
                'video_axis': 'SHORT',
                'delivered': True,
                'delivery_date': '2025-03-18',
                'progress': 100
            }
        ]
    }
]

# 全案件をフラット化（互換性のため）
SAMPLE_CLIENTS = [
    {
        'id': 1,
        'name': 'A社',
        'email': 'contact@company-a.co.jp',
        'phone': '03-1234-5678',
        'company': 'A社',
        'projects_count': 3
    },
    {
        'id': 2,
        'name': 'B社',
        'email': 'info@company-b.co.jp',
        'phone': '03-2345-6789',
        'company': 'B社',
        'projects_count': 2
    },
    {
        'id': 3,
        'name': 'C社',
        'email': 'contact@company-c.co.jp',
        'phone': '03-3456-7890',
        'company': 'C社',
        'projects_count': 1
    }
]

SAMPLE_TASKS = [
    {
        'id': 1,
        'title': '編集作業',
        'project_name': 'WebCM制作プロジェクトA',
        'type': 'EDIT',
        'status': '進行中',
        'assignee': 'テスト',
        'due_date': '2025-02-10',
        'priority': '高'
    },
    {
        'id': 2,
        'title': 'レビュー',
        'project_name': '企業紹介動画制作',
        'type': 'REVIEW',
        'status': '待機中',
        'assignee': 'テスト',
        'due_date': '2025-02-12',
        'priority': '中'
    },
    {
        'id': 3,
        'title': 'サムネイル作成',
        'project_name': 'WebCM制作プロジェクトA',
        'type': 'THUMB',
        'status': '完了',
        'assignee': 'テスト',
        'due_date': '2025-02-08',
        'priority': '低'
    },
    {
        'id': 4,
        'title': '字幕作成',
        'project_name': 'SNS用ショート動画',
        'type': 'CAPTION',
        'status': '完了',
        'assignee': 'テスト',
        'due_date': '2025-01-15',
        'priority': '中'
    }
]

SAMPLE_ASSETS = [
    {
        'id': 1,
        'name': '素材ファイル1.mp4',
        'project_name': 'WebCM制作プロジェクトA',
        'kind': 'raw',
        'size': '125MB',
        'version': 1,
        'uploaded_by': 'テスト',
        'uploaded_at': '2025-01-20'
    },
    {
        'id': 2,
        'name': '完成版_v1.mp4',
        'project_name': '企業紹介動画制作',
        'kind': 'final',
        'size': '89MB',
        'version': 1,
        'uploaded_by': 'テスト',
        'uploaded_at': '2025-02-01'
    },
    {
        'id': 3,
        'name': 'BGM素材.mp3',
        'project_name': 'WebCM制作プロジェクトA',
        'kind': 'music',
        'size': '3.2MB',
        'version': 1,
        'uploaded_by': 'テスト',
        'uploaded_at': '2025-01-18'
    }
]

# 全案件をフラット化（全社統合ビュー用）
def get_all_projects():
    """全会社の案件を統合して返す"""
    all_projects = []
    for company in SAMPLE_COMPANIES:
        for project in company['projects']:
            project_copy = project.copy()
            project_copy['client_name'] = company['name']
            project_copy['company_id'] = company['id']
            all_projects.append(project_copy)
    return all_projects

SAMPLE_PROJECTS = get_all_projects()

# 単価表データ（Google Sheetsの単価表シートから）
SAMPLE_RATE_TABLE = [
    {
        'plan': '長尺YouTube SEO',
        'task': 'YouTubeSEO/動画編集(完成尺20分未満)',
        'bronze': 10000,
        'silver': 12000,
        'gold': 15000,
        'billing_timing': '動画投稿月',
        'evaluation_criteria': '修正回数',
        'notes': 'チーム配属時は「シルバー」スタート'
    },
    {
        'plan': '長尺YouTube SEO',
        'task': 'YouTubeSEO/動画編集延長(5分ごと計算)',
        'bronze': 1000,
        'silver': 1000,
        'gold': 1000,
        'billing_timing': '動画投稿月',
        'evaluation_criteria': '修正回数',
        'notes': '5分ごとに計算'
    },
    {
        'plan': 'ショート動画 YouTube SEOショート',
        'task': 'ショート/動画編集',
        'bronze': 2000,
        'silver': 3000,
        'gold': 3000,
        'billing_timing': '動画投稿月',
        'evaluation_criteria': '修正回数',
        'notes': ''
    }
]

@app.route('/')
def index():
    """ダッシュボード"""
    all_projects = get_all_projects()
    
    # 統計情報を計算
    total_projects = len(all_projects)
    active_projects = len([p for p in all_projects if p['status'] in ['進行中', 'レビュー中']])
    completed_projects = len([p for p in all_projects if p['status'] == '完了'])
    pending_projects = len([p for p in all_projects if p['status'] == '計画中'])
    
    # 会社ごとの統計
    company_stats = []
    for company in SAMPLE_COMPANIES:
        company_projects = company['projects']
        company_stats.append({
            'company': company,
            'total': len(company_projects),
            'active': len([p for p in company_projects if p['status'] in ['進行中', 'レビュー中']]),
            'completed': len([p for p in company_projects if p['status'] == '完了']),
            'assignees': list(set([p.get('assignee', '未割当') for p in company_projects]))
        })
    
    # タスク統計を計算
    total_tasks = len(SAMPLE_TASKS)
    active_tasks = len([t for t in SAMPLE_TASKS if t['status'] in ['進行中', '待機中']])
    completed_tasks = len([t for t in SAMPLE_TASKS if t['status'] == '完了'])
    pending_tasks = len([t for t in SAMPLE_TASKS if t['status'] == '待機中'])
    
    # 最近のタスク（優先度順、期限順）
    recent_tasks = sorted(SAMPLE_TASKS, key=lambda x: (x.get('priority', '中') == '高', x.get('due_date', '')), reverse=True)[:5]
    
    stats = {
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'pending_projects': pending_projects,
        'total_companies': len(SAMPLE_COMPANIES),
        'total_tasks': total_tasks,
        'active_tasks': active_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks
    }
    
    return render_template('index.html', stats=stats, company_stats=company_stats, recent_projects=all_projects[:5], recent_tasks=recent_tasks)

@app.route('/projects')
def projects():
    """案件一覧（全社統合）"""
    company_id = request.args.get('company_id', type=int)
    all_projects = get_all_projects()
    
    # 会社フィルタリング
    if company_id:
        filtered_projects = [p for p in all_projects if p.get('company_id') == company_id]
    else:
        filtered_projects = all_projects
    
    return render_template(
        'projects.html',
        projects=filtered_projects,
        companies=SAMPLE_COMPANIES,
        selected_company_id=company_id,
        project_detail_endpoint='project_detail',
        allow_project_actions=True,
        base_template='layout.html'
    )

@app.route('/companies')
def companies():
    """会社一覧"""
    return render_template(
        'companies.html',
        companies=SAMPLE_COMPANIES,
        company_detail_endpoint='company_detail',
        allow_company_actions=True,
        base_template='layout.html'
    )

@app.route('/companies/<int:company_id>')
def company_detail(company_id):
    """会社詳細（その会社の案件一覧）"""
    company = next((c for c in SAMPLE_COMPANIES if c['id'] == company_id), None)
    if not company:
        return "会社が見つかりません", 404
    
    return render_template(
        'company_detail.html',
        company=company,
        project_detail_endpoint='project_detail',
        company_list_endpoint='companies',
        allow_company_actions=True,
        base_template='layout.html',
        back_url=url_for('companies')
    )

def build_project_detail_context(project_id):
    """案件詳細ページに必要なコンテキストを生成"""
    all_projects = get_all_projects()
    project = next((p for p in all_projects if p['id'] == project_id), None)
    if not project:
        return None

    company = next((c for c in SAMPLE_COMPANIES if c['id'] == project.get('company_id')), None)

    project_tasks = [t for t in SAMPLE_TASKS if t.get('project_name') == project.get('name')]
    if not project_tasks:
        project_tasks = [
            {'id': 1, 'title': '動画編集', 'type': 'EDIT', 'status': '完了' if project.get('delivered') else '進行中', 'assignee': project.get('assignee', '未割当'), 'due_date': project.get('due_date', ''), 'priority': '高'},
            {'id': 2, 'title': 'レビュー', 'type': 'REVIEW', 'status': '完了' if project.get('delivered') else '待機中', 'assignee': 'テスト', 'due_date': project.get('due_date', ''), 'priority': '中'},
            {'id': 3, 'title': '納品', 'type': 'DELIVERY', 'status': '完了' if project.get('delivered') else '未着手', 'assignee': project.get('assignee', '未割当'), 'due_date': project.get('due_date', ''), 'priority': '高'},
        ]

    video_items = [
        {'id': 1, 'axis': 'LONG', 'title': '長尺動画', 'status': '進行中', 'assignee': project.get('assignee', 'テスト'), 'planned_start': project.get('due_date', ''), 'planned_end': project.get('due_date', '')},
        {'id': 2, 'axis': 'SHORT', 'title': 'ショート動画', 'status': '計画中', 'assignee': project.get('assignee', 'テスト'), 'planned_start': project.get('due_date', ''), 'planned_end': project.get('due_date', '')},
    ]

    comments = [
        {'id': 1, 'author': 'テスト', 'content': '素材の確認をお願いします。', 'created_at': '2025-04-01 10:00'},
        {'id': 2, 'author': 'テスト', 'content': '編集作業を開始しました。', 'created_at': '2025-04-02 14:30'},
    ]

    history = [
        {'id': 1, 'action': '案件作成', 'user': 'テスト', 'timestamp': '2025-03-15 09:00'},
        {'id': 2, 'action': 'ステータス変更: 計画中 → 進行中', 'user': 'テスト', 'timestamp': '2025-03-20 10:30'},
        {'id': 3, 'action': '担当者変更', 'user': 'テスト', 'timestamp': '2025-04-01 11:00'},
    ]

    project_assets = [a for a in SAMPLE_ASSETS if a.get('project_name') == project.get('name')]

    return {
        'project': project,
        'company': company,
        'tasks': project_tasks,
        'video_items': video_items,
        'blockers': [],
        'comments': comments,
        'history': history,
        'assets': project_assets
    }


@app.route('/projects/<int:project_id>')
def project_detail(project_id):
    """案件詳細"""
    context = build_project_detail_context(project_id)
    if not context:
        return "案件が見つかりません", 404

    return render_template(
        'project_detail.html',
        base_template='layout.html',
        project_list_endpoint='projects',
        company_detail_endpoint='company_detail',
        back_url=url_for('projects'),
        company_url=url_for('company_detail', company_id=context['company']['id']) if context['company'] else None,
        allow_project_actions=True,
        **context
    )

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """ダッシュボード統計API"""
    all_projects = get_all_projects()
    total = len(all_projects)
    active = len([p for p in all_projects if p['status'] in ['進行中', 'レビュー中']])
    completed = len([p for p in all_projects if p['status'] == '完了'])
    
    return jsonify({
        'status': 'success',
        'data': {
            'total_projects': total,
            'active_projects': active,
            'completed_projects': completed,
            'total_companies': len(SAMPLE_COMPANIES)
        }
    })

@app.route('/api/projects')
def api_projects():
    """案件一覧API"""
    all_projects = get_all_projects()
    return jsonify({
        'status': 'success',
        'data': all_projects
    })

@app.route('/api/companies')
def api_companies():
    """会社一覧API"""
    return jsonify({
        'status': 'success',
        'data': SAMPLE_COMPANIES
    })

@app.route('/api/companies/<int:company_id>')
def api_company_detail(company_id):
    """会社詳細API"""
    company = next((c for c in SAMPLE_COMPANIES if c['id'] == company_id), None)
    if not company:
        return jsonify({'status': 'error', 'message': '会社が見つかりません'}), 404
    
    return jsonify({
        'status': 'success',
        'data': company
    })

@app.route('/api/companies', methods=['POST'])
def api_create_company():
    """会社登録API"""
    data = request.get_json()
    
    # バリデーション
    if not data.get('company_name') or not data.get('company_code'):
        return jsonify({'status': 'error', 'message': '会社名と会社コードは必須です'}), 400
    
    # 会社コードの重複チェック
    existing_company = next((c for c in SAMPLE_COMPANIES if c['code'] == data['company_code']), None)
    if existing_company:
        return jsonify({'status': 'error', 'message': 'この会社コードは既に使用されています'}), 400
    
    # 新しい会社を作成（実際の実装ではデータベースに保存）
    new_company = {
        'id': len(SAMPLE_COMPANIES) + 1,
        'name': data['company_name'],
        'code': data['company_code'],
        'projects': []
    }
    
    # サンプルデータに追加（実際の実装ではデータベースに保存）
    SAMPLE_COMPANIES.append(new_company)
    
    # 専用管理ページのURLを生成
    management_url = f"/companies/{new_company['id']}"
    
    return jsonify({
        'status': 'success',
        'message': '会社が登録されました。専用の管理ページが作成されました。',
        'data': {
            'company': new_company,
            'management_url': management_url
        }
    })

@app.route('/api/projects/<int:project_id>')
def api_project_detail(project_id):
    """案件詳細API"""
    all_projects = get_all_projects()
    project = next((p for p in all_projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404
    
    return jsonify({
        'status': 'success',
        'data': project
    })

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def api_update_project(project_id):
    """案件更新API"""
    data = request.get_json()
    all_projects = get_all_projects()
    
    # 案件を検索
    project_index = None
    company = None
    project = None
    
    for c in SAMPLE_COMPANIES:
        for idx, p in enumerate(c['projects']):
            if p['id'] == project_id:
                project_index = idx
                company = c
                project = p
                break
        if project:
            break
    
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404
    
    # 案件名を更新する前に古い案件名を保存（タスクの案件名も更新するため）
    old_project_name = project.get('name')
    new_project_name = data.get('name', project.get('name'))
    
    # 案件を更新
    project['name'] = new_project_name
    project['due_date'] = data.get('due_date', project.get('due_date'))
    project['assignee'] = data.get('assignee', project.get('assignee'))
    project['completion_length'] = data.get('completion_length', project.get('completion_length'))
    project['video_axis'] = data.get('video_axis', project.get('video_axis', 'LONG'))
    project['status'] = data.get('status', project.get('status', '進行中'))
    project['raw_material_url'] = data.get('raw_material_url', project.get('raw_material_url', ''))
    project['final_video_url'] = data.get('final_video_url', project.get('final_video_url', ''))
    project['script_url'] = data.get('script_url', project.get('script_url', ''))
    project['delivery_date'] = data.get('delivery_date', project.get('delivery_date', ''))
    project['delivered'] = data.get('delivered', project.get('delivered', False))
    
    # 案件名が変更された場合、関連するタスクの案件名も更新
    if old_project_name and new_project_name != old_project_name:
        for task in SAMPLE_TASKS:
            if task.get('project_name') == old_project_name:
                task['project_name'] = new_project_name
    
    # 進捗を計算（納品済みなら100%）
    if project['delivered']:
        project['progress'] = 100
    elif project['status'] == '完了':
        project['progress'] = 100
    elif project['status'] == 'レビュー中':
        project['progress'] = 85
    elif project['status'] == '進行中':
        project['progress'] = 70
    else:
        project['progress'] = 10
    
    return jsonify({
        'status': 'success',
        'message': '案件を更新しました',
        'data': project
    })

@app.route('/api/projects', methods=['POST'])
def api_create_project():
    """案件作成API"""
    data = request.get_json()
    
    # バリデーション
    if not data.get('name') or not data.get('due_date') or not data.get('assignee'):
        return jsonify({'status': 'error', 'message': '企画タイトル、納期、担当は必須です'}), 400
    
    # 区分のデフォルト値
    video_axis = data.get('video_axis', 'LONG')
    if video_axis not in ['LONG', 'SHORT']:
        video_axis = 'LONG'
    
    company_id = data.get('company_id')
    if not company_id:
        return jsonify({'status': 'error', 'message': '会社IDは必須です'}), 400
    
    # 会社を検索
    company = next((c for c in SAMPLE_COMPANIES if c['id'] == company_id), None)
    if not company:
        return jsonify({'status': 'error', 'message': '会社が見つかりません'}), 404
    
    # 新しい案件を作成
    all_projects = get_all_projects()
    new_id = max([p['id'] for p in all_projects], default=0) + 1
    
    new_project = {
        'id': new_id,
        'name': data['name'],
        'due_date': data['due_date'],
        'assignee': data['assignee'],
        'completion_length': data.get('completion_length'),
        'video_axis': video_axis,
        'status': data.get('status', '進行中'),
        'raw_material_url': data.get('raw_material_url', ''),
        'final_video_url': data.get('final_video_url', ''),
        'script_url': data.get('script_url', ''),
        'delivery_date': data.get('delivery_date', ''),
        'delivered': data.get('delivered', False),
        'progress': 10
    }
    
    # 実際の実装ではデータベースに保存
    # ここではサンプルデータに追加
    company['projects'].append(new_project)
    
    return jsonify({
        'status': 'success',
        'message': '案件を追加しました',
        'data': new_project
    })

@app.route('/api/projects/<int:project_id>/toggle-delivered', methods=['POST'])
def api_toggle_delivered(project_id):
    """CLチェックボックスの切り替えAPI"""
    data = request.get_json()
    delivered = data.get('delivered', False)
    
    # 案件を検索
    project = None
    company = None
    
    for c in SAMPLE_COMPANIES:
        for p in c['projects']:
            if p['id'] == project_id:
                project = p
                company = c
                break
        if project:
            break
    
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404
    
    # 納品済み状態を更新
    project['delivered'] = delivered
    
    # 納品済みの場合、納品完了日を設定（24時切り替えで正確に日付を判定）
    if delivered:
        # 日本時間（JST）で現在日時を取得（24時切り替えで正確に日付を判定）
        jst = pytz.timezone('Asia/Tokyo')
        now_jst = datetime.now(jst)
        
        # 日付をYYYY-MM-DD形式で取得（24時切り替えで正確に日付を判定）
        # 例: 2025-01-15 23:59:59 → 2025-01-15
        #     2025-01-16 00:00:00 → 2025-01-16
        delivery_date = now_jst.strftime('%Y-%m-%d')
        
        # CLチェック時は常に現在の日付を設定（既存の完了日を上書き）
        project['delivery_date'] = delivery_date
        
        project['progress'] = 100
        project['status'] = '完了'
    elif not delivered:
        project['delivery_date'] = ''
    
    return jsonify({
        'status': 'success',
        'message': 'CL状態を更新しました',
        'data': {
            'delivered': delivered,
            'delivery_date': project.get('delivery_date', '')
        }
    })

@app.route('/api/data', methods=['GET'])
def get_data():
    """データ取得API"""
    data = {
        'message': 'Hello from Flask!',
        'status': 'success'
    }
    return jsonify(data)

@app.route('/api/data', methods=['POST'])
def post_data():
    """データ送信API"""
    data = request.get_json()
    return jsonify({
        'message': 'Data received',
        'received': data,
        'status': 'success'
    })

@app.route('/clients')
def clients():
    """クライアント一覧（旧名称、companiesにリダイレクト）"""
    return render_template('companies.html', companies=SAMPLE_COMPANIES)

@app.route('/tasks/dashboard')
def task_dashboard():
    """タスク管理ダッシュボード"""
    from datetime import date, timedelta
    
    # 自分のタスクのみを表示（実際の実装ではログインユーザーのタスクを取得）
    my_tasks = SAMPLE_TASKS
    
    # 今日の日付を取得
    today = date.today()
    today_str = today.isoformat()
    
    # 今日のタスク統計
    today_tasks = [t for t in my_tasks if t.get('due_date') == today_str]
    today_completed = len([t for t in today_tasks if t.get('status') == '完了'])
    today_remaining = len(today_tasks) - today_completed
    today_progress = (today_completed / len(today_tasks) * 100) if today_tasks else 0
    
    # 過去7日間の完了タスク数
    past_7_days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        day_tasks = [t for t in my_tasks if t.get('due_date') == day_str and t.get('status') == '完了']
        past_7_days.append({
            'date': day.strftime('%m/%d'),
            'count': len(day_tasks)
        })
    
    # 優先度別タスク数
    high_priority = len([t for t in my_tasks if t.get('priority') == '高'])
    medium_priority = len([t for t in my_tasks if t.get('priority') == '中'])
    low_priority = len([t for t in my_tasks if t.get('priority') == '低'])
    
    # 連続達成日数（サンプルデータ）
    consecutive_days = 0
    
    # 本日の総作業時間（サンプルデータ）
    today_work_time = "00:00"
    
    dashboard_data = {
        'consecutive_days': consecutive_days,
        'today_progress': today_progress,
        'today_completed': today_completed,
        'today_remaining': today_remaining,
        'today_total': len(today_tasks),
        'past_7_days': past_7_days,
        'high_priority': high_priority,
        'medium_priority': medium_priority,
        'low_priority': low_priority,
        'today_work_time': today_work_time
    }
    
    return render_template('task_dashboard.html', 
                         dashboard_data=dashboard_data, 
                         today_tasks=today_tasks,
                         today=today_str)

@app.route('/tasks')
def tasks():
    """タスク作成（自分のタスク）"""
    # 自分のタスクのみを表示（実際の実装ではログインユーザーのタスクを取得）
    # 現在はサンプルデータをそのまま使用
    my_tasks = SAMPLE_TASKS  # 将来的には、自分のタスクのみをフィルタリング
    
    # 今日の日付を取得（期限超過の判定用）
    from datetime import date
    today = date.today().isoformat()
    
    # ページネーション用のパラメータ（将来実装）
    # 現在は全件表示だが、1画面10件表示に対応
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    return render_template('tasks.html', tasks=my_tasks, today=today, page=page, per_page=per_page)

@app.route('/api/tasks')
def api_tasks():
    """タスク一覧API"""
    return jsonify({
        'status': 'success',
        'data': SAMPLE_TASKS
    })

@app.route('/api/tasks/<int:task_id>')
def api_task_detail(task_id):
    """タスク詳細API"""
    task = next((t for t in SAMPLE_TASKS if t['id'] == task_id), None)
    if not task:
        return jsonify({'status': 'error', 'message': 'タスクが見つかりません'}), 404
    
    return jsonify({
        'status': 'success',
        'data': task
    })

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    """タスク更新API"""
    data = request.get_json()
    task = next((t for t in SAMPLE_TASKS if t['id'] == task_id), None)
    
    if not task:
        return jsonify({'status': 'error', 'message': 'タスクが見つかりません'}), 404
    
    # タスクを更新
    task['title'] = data.get('title', task['title'])
    task['project_name'] = data.get('project_name', task.get('project_name'))
    task['type'] = data.get('type', task.get('type'))
    task['status'] = data.get('status', task.get('status', '待機中'))
    task['assignee'] = data.get('assignee', task.get('assignee'))
    task['due_date'] = data.get('due_date', task.get('due_date'))
    task['priority'] = data.get('priority', task.get('priority', '中'))
    if 'progress' in data:
        task['progress'] = data['progress']
    
    return jsonify({
        'status': 'success',
        'message': 'タスクを更新しました',
        'data': task
    })

@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    """タスク作成API"""
    data = request.get_json()
    
    # バリデーション
    if not data.get('title'):
        return jsonify({'status': 'error', 'message': 'タスク名は必須です'}), 400
    
    # 新しいタスクを作成
    new_id = max([t['id'] for t in SAMPLE_TASKS], default=0) + 1
    
    new_task = {
        'id': new_id,
        'title': data.get('title'),
        'project_name': data.get('project_name', ''),
        'type': data.get('type', 'EDIT'),
        'status': data.get('status', '待機中'),
        'assignee': data.get('assignee', 'テスト'),
        'due_date': data.get('due_date', ''),
        'priority': data.get('priority', '中')
    }
    
    # サンプルデータに追加（実際の実装ではデータベースに保存）
    SAMPLE_TASKS.append(new_task)
    
    return jsonify({
        'status': 'success',
        'message': 'タスクを追加しました',
        'data': new_task
    })

@app.route('/assets')
def assets():
    """素材管理"""
    all_projects = get_all_projects()
    return render_template('assets.html', assets=SAMPLE_ASSETS, projects=all_projects)

@app.route('/finance')
def finance():
    """請求・収支"""
    # サンプルデータ
    finance_data = {
        'total_revenue': 1500000,
        'total_cost': 800000,
        'profit': 700000,
        'profit_rate': 46.7,
        'invoices': [
            {'id': 1, 'project_name': 'WebCM制作プロジェクトA', 'amount': 500000, 'status': 'paid', 'issue_date': '2025-01-20'},
            {'id': 2, 'project_name': '企業紹介動画制作', 'amount': 800000, 'status': 'issued', 'issue_date': '2025-02-01'},
            {'id': 3, 'project_name': 'SNS用ショート動画', 'amount': 200000, 'status': 'paid', 'issue_date': '2024-12-15'},
        ],
        'payouts': [
            {'id': 1, 'editor': 'テスト', 'amount': 300000, 'project_name': 'WebCM制作プロジェクトA', 'status': 'paid'},
            {'id': 2, 'editor': 'テスト', 'amount': 250000, 'project_name': '企業紹介動画制作', 'status': 'pending'},
            {'id': 3, 'editor': 'テスト', 'amount': 150000, 'project_name': 'SNS用ショート動画', 'status': 'paid'},
        ]
    }
    return render_template('finance.html', finance_data=finance_data)

@app.route('/reports')
def reports():
    """レポート"""
    return render_template('reports.html')

@app.route('/settings')
@login_required
def settings():
    """設定"""
    quick_links_text = "\n".join(
        f"{link.get('label', '')} | {link.get('url', '')} | {link.get('description', '')}"
        for link in EDITOR_SHARED_SETTINGS.get('quick_links', [])
    )
    notices_text = "\n".join(
        f"{notice.get('title', '')} | {notice.get('body', '')}"
        for notice in EDITOR_SHARED_SETTINGS.get('pinned_notices', [])
    )
    workspace_updated = request.args.get('workspace_updated') == '1'
    return render_template(
        'settings.html',
        rate_table=SAMPLE_RATE_TABLE,
        editor_settings=EDITOR_SHARED_SETTINGS,
        editor_workspace_quick_links=quick_links_text,
        editor_workspace_notices=notices_text,
        workspace_updated=workspace_updated
    )


@app.route('/settings/editor-workspace', methods=['POST'])
@login_required
@role_required('admin')
def update_editor_workspace_settings():
    description = request.form.get('workspace_description', '').strip()
    show_quick_links = request.form.get('show_quick_links') == 'on'
    show_pinned_notices = request.form.get('show_pinned_notices') == 'on'
    quick_links_raw = request.form.get('quick_links', '')
    notices_raw = request.form.get('pinned_notices', '')

    quick_links = []
    for line in quick_links_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) >= 2:
            link = {
                'label': parts[0],
                'url': parts[1],
                'description': parts[2] if len(parts) >= 3 else ''
            }
            quick_links.append(link)

    pinned_notices = []
    today_str = datetime.now().strftime('%Y-%m-%d')
    for line in notices_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split('|')]
        if parts[0]:
            notice = {
                'title': parts[0],
                'body': parts[1] if len(parts) >= 2 else '',
                'updated_at': today_str
            }
            pinned_notices.append(notice)

    execute(
        """
        update app.editor_shared_settings
        set
            description = :description,
            show_quick_links = :show_quick_links,
            show_pinned_notices = :show_pinned_notices,
            quick_links = :quick_links,
            pinned_notices = :pinned_notices,
            updated_at = :updated_at
        where id = :id
        """,
        description=description,
        show_quick_links=show_quick_links,
        show_pinned_notices=show_pinned_notices,
        quick_links=json.dumps(quick_links),
        pinned_notices=json.dumps(pinned_notices),
        updated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        id=EDITOR_SHARED_SETTINGS['id']
    )

    load_editor_shared_settings()
    return redirect(url_for('settings', workspace_updated='1'))

@app.route('/board')
def board():
    """案件ボード（ガントチャート風）"""
    all_projects = get_all_projects()
    return render_template('board.html', projects=all_projects, companies=SAMPLE_COMPANIES)


@app.route('/editor')
@login_required
@role_required('admin', 'editor')
def editor_dashboard():
    """編集者向けダッシュボード"""
    all_projects = get_all_projects()
    current_user = g.current_user
    workspace = get_editor_workspace_for_user(current_user)
    editor_keyword = current_user.get('name', '') if current_user and current_user.get('name') else 'テスト'

    assigned_projects = [
        p for p in all_projects
        if p.get('assignee') and editor_keyword in p.get('assignee')
    ]

    def parse_due_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None

    sorted_projects = sorted(
        assigned_projects,
        key=lambda p: (parse_due_date(p.get('due_date')) or datetime.max)
    )

    status_counts = {
        'in_progress': len([p for p in assigned_projects if p.get('status') == '進行中']),
        'review': len([p for p in assigned_projects if p.get('status') == 'レビュー中']),
        'completed': len([p for p in assigned_projects if p.get('status') == '完了'])
    }

    today_str = datetime.now().date().isoformat()
    today_tasks = [
        t for t in SAMPLE_TASKS
        if t.get('due_date') == today_str and t.get('assignee') == 'テスト'
    ]

    pending_assets = [
        {
            'name': asset.get('name'),
            'project_name': asset.get('project_name'),
            'url': asset.get('url') or url_for('assets')
        }
        for asset in SAMPLE_ASSETS
    ][:5]

    dashboard_data = {
        'total_assigned_projects': len(assigned_projects),
        'today_tasks_count': len(today_tasks),
        'status_counts': status_counts,
        'next_due_project': sorted_projects[0] if sorted_projects else None,
        'assigned_projects': sorted_projects[:6],
        'today_tasks': today_tasks,
        'pending_assets': pending_assets
    }

    return render_template(
        'editor/index.html',
        dashboard_data=dashboard_data,
        workspace=workspace
    )


@app.route('/editor/projects')
@login_required
@role_required('admin', 'editor')
def editor_projects():
    """編集者向け案件一覧"""
    company_id = request.args.get('company_id', type=int)
    all_projects = get_all_projects()

    if company_id:
        filtered_projects = [p for p in all_projects if p.get('company_id') == company_id]
    else:
        filtered_projects = all_projects

    return render_template(
        'projects.html',
        projects=filtered_projects,
        companies=SAMPLE_COMPANIES,
        selected_company_id=company_id,
        project_detail_endpoint='editor_project_detail',
        allow_project_actions=False,
        base_template='editor_layout.html'
    )


@app.route('/editor/projects/<int:project_id>')
@login_required
@role_required('admin', 'editor')
def editor_project_detail(project_id):
    """編集者向け案件詳細"""
    context = build_project_detail_context(project_id)
    if not context:
        return "案件が見つかりません", 404

    company = context.get('company')

    return render_template(
        'project_detail.html',
        base_template='editor_layout.html',
        project_list_endpoint='editor_projects',
        company_detail_endpoint='editor_company_detail',
        back_url=url_for('editor_projects'),
        company_url=url_for('editor_company_detail', company_id=company['id']) if company else None,
        allow_project_actions=False,
        **context
    )


@app.route('/editor/board')
@login_required
@role_required('admin', 'editor')
def editor_board():
    """編集者向け案件ボード"""
    all_projects = get_all_projects()
    return render_template(
        'board.html',
        projects=all_projects,
        companies=SAMPLE_COMPANIES,
        base_template='editor_layout.html'
    )


@app.route('/editor/assets')
@login_required
@role_required('admin', 'editor')
def editor_assets():
    """編集者向け素材管理"""
    all_projects = get_all_projects()
    return render_template(
        'assets.html',
        assets=SAMPLE_ASSETS,
        projects=all_projects,
        base_template='editor_layout.html'
    )


@app.route('/editor/companies')
@login_required
@role_required('admin', 'editor')
def editor_companies():
    """編集者向け会社一覧"""
    return render_template(
        'companies.html',
        companies=SAMPLE_COMPANIES,
        company_detail_endpoint='editor_company_detail',
        allow_company_actions=False,
        base_template='editor_layout.html'
    )


@app.route('/editor/companies/<int:company_id>')
@login_required
@role_required('admin', 'editor')
def editor_company_detail(company_id):
    """編集者向け会社詳細"""
    company = next((c for c in SAMPLE_COMPANIES if c['id'] == company_id), None)
    if not company:
        return "会社が見つかりません", 404

    all_projects = get_all_projects()
    company_projects = [p for p in all_projects if p.get('company_id') == company_id]
    company_context = company.copy()
    company_context['projects'] = company_projects

    return render_template(
        'company_detail.html',
        company=company_context,
        project_detail_endpoint='editor_project_detail',
        company_list_endpoint='editor_companies',
        allow_company_actions=False,
        base_template='editor_layout.html',
        back_url=url_for('editor_companies')
    )

def parse_japanese_date(date_str):
    """日本語形式の日付をYYYY-MM-DD形式に変換"""
    if not date_str or date_str.strip() == '':
        return None
    
    # MM/DD形式
    if re.match(r'^\d{1,2}/\d{1,2}$', date_str):
        parts = date_str.split('/')
        month = int(parts[0])
        day = int(parts[1])
        current_year = datetime.now().year
        try:
            return datetime(current_year, month, day).strftime('%Y-%m-%d')
        except:
            return None
    
    # YYYY/MM/DD形式
    if re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', date_str):
        parts = date_str.split('/')
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        try:
            return datetime(year, month, day).strftime('%Y-%m-%d')
        except:
            return None
    
    # MM月DD日(曜日)形式
    match = re.match(r'(\d{1,2})月(\d{1,2})日', date_str)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        current_year = datetime.now().year
        try:
            return datetime(current_year, month, day).strftime('%Y-%m-%d')
        except:
            return None
    
    return None

def parse_assignee(assignee_str):
    """担当者名から"(完)"や"(未)"のプレフィックスを処理"""
    if not assignee_str:
        return None
    
    # "(完)"や"(未)"を除去
    assignee = assignee_str.replace('(完)', '').replace('(未)', '').strip()
    return assignee if assignee else None

def parse_checkbox(checkbox_str):
    """チェックボックスやチェックマークを真偽値に変換"""
    if not checkbox_str:
        return False
    
    checkbox_str = str(checkbox_str).strip().upper()
    # チェックマーク、✓、☑、✓、TRUE、1などをTrueに
    return checkbox_str in ['TRUE', '1', '✓', '☑', '✔', 'チェック済', '済', '○', 'YES', 'Y']

@app.route('/api/import/csv', methods=['POST'])
def import_csv():
    """CSVファイルをインポート"""
    if 'csv_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'CSVファイルが指定されていません'}), 400
    
    file = request.files['csv_file']
    import_type = request.form.get('import_type', 'projects')
    
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'ファイルが選択されていません'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'status': 'error', 'message': 'CSVファイルを選択してください'}), 400
    
    try:
        # CSVファイルを読み込む
        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        
        imported_count = 0
        skipped_count = 0
        
        # 既存の最大IDを取得
        all_projects = get_all_projects()
        max_project_id = max([p['id'] for p in all_projects]) if all_projects else 0
        
        for row in reader:
            try:
                if import_type == 'projects':
                    # 案件管理シート形式: 納期、ID、企画タイトル、動画担当、CL✔、元素材、納品動画、台本、納品完了日
                    due_date = parse_japanese_date(row.get('納期', ''))
                    project_id = row.get('ID', '').strip()
                    title = row.get('企画タイトル', '').strip()
                    assignee = parse_assignee(row.get('動画担当', ''))
                    cl_checked = parse_checkbox(row.get('CL✔', ''))
                    raw_material = row.get('元素材', '').strip()
                    delivery_video = row.get('納品動画', '').strip()
                    script = row.get('台本', '').strip()
                    delivery_date = parse_japanese_date(row.get('納品完了日', ''))
                    
                    if not title:
                        skipped_count += 1
                        continue
                    
                    # 既存の案件を更新または新規作成
                    if project_id:
                        # IDがある場合は既存案件を探す
                        existing_project = next((p for p in all_projects if str(p['id']) == str(project_id)), None)
                        if existing_project:
                            # 既存案件を更新
                            if due_date:
                                existing_project['due_date'] = due_date
                            if assignee:
                                existing_project['assignee'] = assignee
                            if raw_material:
                                existing_project['raw_material_url'] = raw_material
                            if delivery_video:
                                existing_project['final_video_url'] = delivery_video
                            if script:
                                existing_project['script_url'] = script
                            if delivery_date:
                                existing_project['delivery_date'] = delivery_date
                            if cl_checked:
                                existing_project['delivered'] = True
                                existing_project['status'] = '完了'
                                existing_project['progress'] = 100
                            imported_count += 1
                        else:
                            # 新規案件を作成
                            max_project_id += 1
                            new_project = {
                                'id': max_project_id,
                                'name': title,
                                'status': '完了' if cl_checked else '進行中',
                                'due_date': due_date or '',
                                'assignee': assignee or '未割当',
                                'completion_length': None,
                                'video_axis': 'LONG',
                                'delivered': cl_checked,
                                'delivery_date': delivery_date or '',
                                'progress': 100 if cl_checked else 0,
                                'raw_material_url': raw_material,
                                'final_video_url': delivery_video,
                                'script_url': script,
                                'company_id': 1  # デフォルトで最初の会社に紐付け
                            }
                            # 会社に追加
                            if SAMPLE_COMPANIES:
                                SAMPLE_COMPANIES[0]['projects'].append(new_project)
                            imported_count += 1
                    else:
                        skipped_count += 1
                
                elif import_type == 'video_editing':
                    # 動画編集管理シート形式: 納期、ID、企画タイトル、完成尺、担当、納品済、元素材、納品動画、画面キャプチャ素材、完パケ
                    due_date = parse_japanese_date(row.get('納期', ''))
                    project_id = row.get('ID', '').strip()
                    title = row.get('企画タイトル', '').strip()
                    completion_length = row.get('完成尺', '').strip()
                    assignee = parse_assignee(row.get('担当', ''))
                    delivered = parse_checkbox(row.get('納品済', ''))
                    raw_material = row.get('元素材', '').strip()
                    delivery_video = row.get('納品動画', '').strip()
                    screenshot_material = row.get('画面キャプチャ素材', '').strip()
                    final_package = row.get('完パケ', '').strip()
                    
                    if not title:
                        skipped_count += 1
                        continue
                    
                    # 完成尺を数値に変換
                    try:
                        completion_length_int = int(completion_length) if completion_length else None
                    except:
                        completion_length_int = None
                    
                    max_project_id += 1
                    new_project = {
                        'id': max_project_id,
                        'name': title,
                        'status': '完了' if delivered else '進行中',
                        'due_date': due_date or '',
                        'assignee': assignee or '未割当',
                        'completion_length': completion_length_int,
                        'video_axis': 'LONG',
                        'delivered': delivered,
                        'delivery_date': '',
                        'progress': 100 if delivered else 0,
                        'raw_material_url': raw_material,
                        'final_video_url': delivery_video,
                        'script_url': '',
                        'company_id': 1
                    }
                    
                    if SAMPLE_COMPANIES:
                        SAMPLE_COMPANIES[0]['projects'].append(new_project)
                    imported_count += 1
                
                elif import_type == 'projects_alt':
                    # 案件管理シート（別形式）: ID、企画タイトル、納期、担当、CL✔、動画素材、完成動画、台本、納品完了日、支払い済
                    project_id = row.get('ID', '').strip()
                    title = row.get('企画タイトル', '').strip()
                    due_date = parse_japanese_date(row.get('納期', ''))
                    assignee = parse_assignee(row.get('担当', ''))
                    cl_checked = parse_checkbox(row.get('CL✔', ''))
                    raw_material = row.get('動画素材', '').strip()
                    delivery_video = row.get('完成動画', '').strip()
                    script = row.get('台本', '').strip()
                    delivery_date = parse_japanese_date(row.get('納品完了日', ''))
                    paid = parse_checkbox(row.get('支払い済', ''))
                    
                    if not title:
                        skipped_count += 1
                        continue
                    
                    if project_id:
                        existing_project = next((p for p in all_projects if str(p['id']) == str(project_id)), None)
                        if existing_project:
                            if due_date:
                                existing_project['due_date'] = due_date
                            if assignee:
                                existing_project['assignee'] = assignee
                            if raw_material:
                                existing_project['raw_material_url'] = raw_material
                            if delivery_video:
                                existing_project['final_video_url'] = delivery_video
                            if script:
                                existing_project['script_url'] = script
                            if delivery_date:
                                existing_project['delivery_date'] = delivery_date
                            if cl_checked:
                                existing_project['delivered'] = True
                                existing_project['status'] = '完了'
                                existing_project['progress'] = 100
                            imported_count += 1
                        else:
                            max_project_id += 1
                            new_project = {
                                'id': max_project_id,
                                'name': title,
                                'status': '完了' if cl_checked else '進行中',
                                'due_date': due_date or '',
                                'assignee': assignee or '未割当',
                                'completion_length': None,
                                'video_axis': 'LONG',
                                'delivered': cl_checked,
                                'delivery_date': delivery_date or '',
                                'progress': 100 if cl_checked else 0,
                                'raw_material_url': raw_material,
                                'final_video_url': delivery_video,
                                'script_url': script,
                                'company_id': 1
                            }
                            if SAMPLE_COMPANIES:
                                SAMPLE_COMPANIES[0]['projects'].append(new_project)
                            imported_count += 1
                    else:
                        skipped_count += 1
                
            except Exception as e:
                skipped_count += 1
                continue
        
        return jsonify({
            'status': 'success',
            'message': f'CSVインポートが完了しました',
            'data': {
                'imported_count': imported_count,
                'skipped_count': skipped_count
            }
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'CSVインポート中にエラーが発生しました: {str(e)}'
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if getattr(g, 'current_user', None):
        next_url = request.args.get('next')
        return redirect(next_url or url_for('index'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        next_url = request.form.get('next')

        user = get_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            error = 'メールアドレスまたはパスワードが正しくありません。'
        elif not user.get('active', True):
            error = 'このユーザーは無効化されています。管理者に連絡してください。'
        else:
            session['user_id'] = user['id']
            return redirect(next_url or url_for('index'))

    next_url = request.args.get('next')
    return render_template('auth/login.html', error=error, next_url=next_url)


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.pop('user_id', None)
    next_url = request.form.get('next') or url_for('login')
    return redirect(next_url)


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_users():
    error = None
    success = None
    form_data = {}

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', 'editor').strip().lower()
        password = request.form.get('password', '').strip()
        active = request.form.get('active') == 'on'

        form_data = {
            'name': name,
            'email': email,
            'role': role,
            'active': active
        }

        allowed_roles = {'admin', 'editor', 'client'}
        if role not in allowed_roles:
            role = 'editor'

        errors = []
        if not name:
            errors.append('氏名は必須です。')
        if not email:
            errors.append('メールアドレスは必須です。')
        elif get_user_by_email(email):
            errors.append('このメールアドレスは既に登録されています。')
        if not password or len(password) < 6:
            errors.append('パスワードは6文字以上で入力してください。')

        if errors:
            error = '\n'.join(errors)
        else:
            new_user = create_user(
                name=name,
                email=email,
                role=role,
                password_hash=generate_password_hash(password),
                active=active
            )
            workspace_message = ''
            if new_user['role'] == 'editor':
                create_editor_workspace_for_user(new_user)
                workspace_message = ' 編集者用共有ページも自動生成されました。'
            success = f'ユーザーを作成しました。初期パスワードを共有してください。{workspace_message}'
            form_data = {}

    return render_template(
        'admin/users.html',
        users=list_users(),
        role_labels=ROLE_LABELS,
        error=error,
        success=success,
        form_data=form_data
    )

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5001)

