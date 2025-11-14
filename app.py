from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    url_for,
    redirect,
    session,
    g,
    abort,
    send_from_directory,
    send_file,
    has_request_context
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
from itertools import count
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from werkzeug.utils import secure_filename
from uuid import uuid4
from io import BytesIO

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

load_dotenv()

app = Flask(__name__)
CORS(app)

# 静的ファイルとテンプレートのパスを設定
app.config['STATIC_FOLDER'] = 'static'
app.config['TEMPLATES_FOLDER'] = 'templates'
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')

PRIMARY_OWNER_EMAIL = os.environ.get('PRIMARY_OWNER_EMAIL', 'keisuke030742@gmail.com')
PRIMARY_OWNER_PASSWORD = os.environ.get('PRIMARY_OWNER_PASSWORD', '1234')
PRIMARY_OWNER_NAME = os.environ.get('PRIMARY_OWNER_NAME', '大田圭介')
PRIMARY_OWNER_ROLE = os.environ.get('PRIMARY_OWNER_ROLE', 'admin')

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

TASK_TYPE_LABELS = {
    'EDIT': '編集',
    'REVIEW': 'レビュー',
    'THUMB': 'サムネイル',
    'CAPTION': '字幕',
    'DELIVERY': '納品',
    'PLAN': '企画',
    'SHOOT': '撮影',
    'SCRIPT': '台本',
    'MEETING': '打ち合わせ',
    'OTHER': 'その他'
}

PASSWORD_HASH_METHOD = os.environ.get('PASSWORD_HASH_METHOD', 'pbkdf2:sha256')


def hash_password(password: str) -> str:
    """環境に依存しない安全なパスワードハッシュを生成"""
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


TRAINING_STATUS_OPTIONS = ['未視聴', '視聴中', '視聴済', '要復習']


def serialize_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        return value
    return value.strftime('%Y-%m-%d %H:%M')


def normalize_percent(value):
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def allowed_training_video_filename(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_TRAINING_VIDEO_EXTENSIONS


ALLOWED_TRAINING_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'wmv', 'm4v'}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINING_VIDEO_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads', 'training_videos')
os.makedirs(TRAINING_VIDEO_UPLOAD_FOLDER, exist_ok=True)

VIDEO_ITEM_ID_COUNTER = count(1)
COMMENT_ID_COUNTER = count(1)
PROJECT_VIDEO_ITEMS = {}
PROJECT_COMMENTS = {}
PROJECT_STATUS_HISTORY = {}

MAX_PROJECT_STATUS_TIMELINE_DAYS = 180
STATUS_HISTORY_DEFAULT_ACTOR = 'システム'

FINANCE_INVOICE_STATUS_DEFINITIONS = [
    ('draft', '下書き'),
    ('issued', '発行済'),
    ('sent', '送付済'),
    ('paid', '入金済'),
    ('overdue', '入金遅延')
]
FINANCE_PAYOUT_STATUS_DEFINITIONS = [
    ('pending', '未支払'),
    ('scheduled', '支払予定'),
    ('paid', '支払済')
]

FINANCE_INVOICE_STATUS_OPTIONS = [
    {'value': value, 'label': label} for value, label in FINANCE_INVOICE_STATUS_DEFINITIONS
]
FINANCE_PAYOUT_STATUS_OPTIONS = [
    {'value': value, 'label': label} for value, label in FINANCE_PAYOUT_STATUS_DEFINITIONS
]
FINANCE_INVOICE_STATUS_LABELS = {value: label for value, label in FINANCE_INVOICE_STATUS_DEFINITIONS}
FINANCE_PAYOUT_STATUS_LABELS = {value: label for value, label in FINANCE_PAYOUT_STATUS_DEFINITIONS}

FINANCE_INVOICES = [
    {'id': 1, 'project_name': 'WebCM制作プロジェクトA', 'amount': 500000, 'status': 'paid', 'issue_date': '2025-01-20'},
    {'id': 2, 'project_name': '企業紹介動画制作', 'amount': 800000, 'status': 'issued', 'issue_date': '2025-02-01'},
    {'id': 3, 'project_name': 'SNS用ショート動画', 'amount': 200000, 'status': 'paid', 'issue_date': '2024-12-15'},
]
FINANCE_PAYOUTS = [
    {'id': 1, 'editor': '田中', 'amount': 300000, 'project_name': 'WebCM制作プロジェクトA', 'status': 'paid'},
    {'id': 2, 'editor': '佐藤', 'amount': 250000, 'project_name': '企業紹介動画制作', 'status': 'pending'},
    {'id': 3, 'editor': '鈴木', 'amount': 150000, 'project_name': 'SNS用ショート動画', 'status': 'paid'},
]

FINANCE_INVOICE_ID_COUNTER = count(start=len(FINANCE_INVOICES) + 1)
FINANCE_PAYOUT_ID_COUNTER = count(start=len(FINANCE_PAYOUTS) + 1)

REPORT_PDF_FONT_NAME = 'HeiseiKakuGo-W5'
REPORT_PDF_FONT_REGISTERED = False


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
        """,
        """
        create table if not exists app.training_videos (
            id serial primary key,
            title varchar(255) not null,
            description text,
            url text not null,
            duration_minutes integer,
            created_by integer references app.users(id),
            created_at timestamp default now()
        );
        """,
        """
        create table if not exists app.training_video_progress (
            video_id integer not null references app.training_videos(id) on delete cascade,
            user_id integer not null references app.users(id) on delete cascade,
            status varchar(50) not null default '未視聴',
            progress_percent integer not null default 0,
            last_viewed_at timestamp default now(),
            notes text,
            primary key (video_id, user_id)
        );
        """,
        """
        create index if not exists idx_training_video_progress_status
        on app.training_video_progress(status);
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
            password_hash=hash_password('adminpass'),
            active=True
        )

    editor = get_user_by_email('editor@example.com')
    if not editor:
        editor = create_user(
            name='テスト編集者',
            email='editor@example.com',
            role='editor',
            password_hash=hash_password('editorpass'),
            active=True
        )

    if editor:
        create_editor_workspace_for_user(editor)

    ensure_primary_owner_account()


def ensure_primary_owner_account():
    owner_email = (PRIMARY_OWNER_EMAIL or '').strip().lower()
    if not owner_email:
        return

    desired_role = (PRIMARY_OWNER_ROLE or 'admin').strip().lower()
    if desired_role not in {'admin', 'editor', 'client'}:
        desired_role = 'admin'

    owner = get_user_by_email(owner_email)
    password_hash_value = hash_password(PRIMARY_OWNER_PASSWORD or '1234')

    if owner:
        execute(
            """
            update app.users
            set name = :name,
                role = :role,
                password_hash = :password_hash,
                active = true
            where id = :id
            """,
            name=PRIMARY_OWNER_NAME or owner.get('name') or 'オーナー',
            role=desired_role,
            password_hash=password_hash_value,
            id=owner['id']
        )
        owner = get_user_by_email(owner_email)
    else:
        owner = create_user(
            name=PRIMARY_OWNER_NAME or 'オーナー',
            email=owner_email,
            role=desired_role,
            password_hash=password_hash_value,
            active=True
        )

    if owner.get('role') == 'editor':
        create_editor_workspace_for_user(owner)
    if owner.get('role') == 'client':
        ensure_client_portal_profile(owner)


def ensure_default_training_videos():
    count_row = fetch_one("select count(1) as cnt from app.training_videos")
    if count_row and count_row['cnt'] > 0:
        return

    admin = get_user_by_email('admin@example.com')
    admin_id = admin['id'] if admin else None

    default_videos = [
        {
            'title': '編集ルール基礎講座',
            'description': '編集方針・命名規則・納品までの流れをまとめた社内向け動画です。',
            'url': 'https://example.com/videos/editing-basics.mp4',
            'duration_minutes': 18
        },
        {
            'title': 'Premiere Pro ワークフロー',
            'description': 'プロジェクトテンプレートの使い方と書き出し設定の解説です。',
            'url': 'https://example.com/videos/premiere-workflow.mp4',
            'duration_minutes': 24
        }
    ]

    inserted_ids = []
    with engine.begin() as conn:
        for video in default_videos:
            result = conn.execute(
                text(
                    """
                    insert into app.training_videos (title, description, url, duration_minutes, created_by)
                    values (:title, :description, :url, :duration_minutes, :created_by)
                    returning id
                    """
                ),
                {
                    'title': video['title'],
                    'description': video['description'],
                    'url': video['url'],
                    'duration_minutes': video['duration_minutes'],
                    'created_by': admin_id
                }
            )
            inserted_ids.append(result.scalar())

    editor = get_user_by_email('editor@example.com')
    if editor and inserted_ids:
        progress_samples = [
            {'status': '視聴済', 'progress_percent': 100},
            {'status': '視聴中', 'progress_percent': 45}
        ]
        with engine.begin() as conn:
            for idx, sample in enumerate(progress_samples):
                if idx >= len(inserted_ids):
                    break
                conn.execute(
                    text(
                        """
                        insert into app.training_video_progress (video_id, user_id, status, progress_percent, last_viewed_at)
                        values (:video_id, :user_id, :status, :progress_percent, :last_viewed_at)
                        on conflict (video_id, user_id)
                        do update set
                            status = excluded.status,
                            progress_percent = excluded.progress_percent,
                            last_viewed_at = excluded.last_viewed_at
                        """
                    ),
                    {
                        'video_id': inserted_ids[idx],
                        'user_id': editor['id'],
                        'status': sample['status'],
                        'progress_percent': sample['progress_percent'],
                        'last_viewed_at': datetime.now() - timedelta(days=1)
                    }
                )


ensure_tables()
load_editor_shared_settings()
ensure_default_users()
ensure_default_training_videos()

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


def get_default_home_endpoint(role: str | None) -> str:
    if role == 'client':
        return 'client_dashboard'
    if role == 'editor':
        return 'editor_dashboard'
    return 'index'


def is_client_allowed_endpoint(endpoint_name: str | None) -> bool:
    if not endpoint_name:
        return False
    if endpoint_name in {'client_dashboard', 'logout'}:
        return True
    if endpoint_name.startswith('client_'):
        return True
    return False


def normalize_next_url(raw_value, default_endpoint=None):
    if not raw_value:
        return url_for(default_endpoint) if default_endpoint else None

    value = str(raw_value).strip()
    if value.lower() in {'none', 'null', 'undefined'}:
        return url_for(default_endpoint) if default_endpoint else None

    parsed = urlparse(value)

    if parsed.scheme and parsed.scheme not in {'http', 'https'}:
        return url_for(default_endpoint) if default_endpoint else None

    if parsed.netloc and parsed.netloc != request.host:
        return url_for(default_endpoint) if default_endpoint else None

    next_path = parsed.path or '/'
    if parsed.query:
        next_path = f"{next_path}?{parsed.query}"

    return next_path or (url_for(default_endpoint) if default_endpoint else None)


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

    if current_user.get('role') == 'client':
        if not is_client_allowed_endpoint(endpoint_root):
            return redirect(url_for('client_dashboard'))


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
                'color': '#3b82f6',
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
                'color': '#facc15',
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
                'color': '#22c55e',
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
                'color': '#f97316',
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
                'color': '#ef4444',
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
                'color': '#8b5cf6',
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

CLIENT_FINAL_ASSET_KINDS = {'final', 'delivery', '納品', 'complete', 'final_cut'}
CLIENT_PORTAL_PROFILES: dict[int, dict] = {}

TASK_ID_COUNTER = count(20000)
PROJECT_GANTT_TASKS: dict[int, list[dict]] = {}
GENERAL_TASKS: list[dict] = []
TASK_CACHE: list[dict] = []

AUTO_STAGE_TEMPLATES = [
    {'key': 'plan', 'title': '企画・準備', 'duration': 4},
    {'key': 'materials', 'title': '素材整理・収集', 'duration': 3},
    {'key': 'edit', 'title': '編集', 'duration': 5},
    {'key': 'review', 'title': 'レビュー・調整', 'duration': 3},
    {'key': 'delivery', 'title': '納品', 'duration': 1},
]

PROJECT_COLOR_PALETTE = [
    '#3b82f6',  # blue
    '#facc15',  # amber
    '#22c55e',  # green
    '#f87171',  # red
    '#8b5cf6',  # purple
    '#14b8a6',  # teal
    '#f97316',  # orange
    '#64748b',  # slate
]
PROJECT_COLOR_ASSIGNMENTS: dict[int, list[str]] = {}


def ensure_client_portal_profile(user: dict | None):
    if not user:
        return None
    profile = CLIENT_PORTAL_PROFILES.get(user['id'])
    display_name = f"{user['name']}さんのポータル"
    if not profile:
        profile = {
            'user_id': user['id'],
            'owner_name': user['name'],
            'display_name': display_name,
            'welcome_message': '案件の進捗・納品状況をこちらでリアルタイムに確認できます。',
            'project_scope_label': '全案件を表示中',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        CLIENT_PORTAL_PROFILES[user['id']] = profile
    else:
        profile['owner_name'] = user['name']
        profile['display_name'] = display_name
    return profile


def get_client_portal_profile(user_id: int):
    return CLIENT_PORTAL_PROFILES.get(user_id)


def parse_iso_date(value, fallback=None):
    if not value:
        return fallback
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return fallback


def isoformat_date(date_obj):
    return date_obj.strftime('%Y-%m-%d')


def next_task_id():
    return next(TASK_ID_COUNTER)


def ensure_project_color(company_id: int, project: dict) -> str:
    if project.get('color'):
        color = project['color']
        assigned = PROJECT_COLOR_ASSIGNMENTS.setdefault(company_id, [])
        if color not in assigned:
            assigned.append(color)
        return color

    assigned = PROJECT_COLOR_ASSIGNMENTS.setdefault(company_id, [])
    palette = PROJECT_COLOR_PALETTE
    available = [c for c in palette if c not in assigned]
    if not available:
        color = palette[len(assigned) % len(palette)]
    else:
        color = available[0]
    project['color'] = color
    assigned.append(color)
    return color


def build_auto_gantt_tasks(project: dict, company_name: str, color: str):
    axis = project.get('video_axis', 'LONG')
    stage_templates = []
    for template in AUTO_STAGE_TEMPLATES:
        tpl = template.copy()
        if tpl['key'] == 'edit':
            tpl['duration'] = 5 if axis == 'LONG' else 3
        if tpl['key'] == 'delivery':
            tpl['duration'] = 1 if project.get('delivered') else tpl['duration']
        stage_templates.append(tpl)

    default_due = datetime.now().date() + timedelta(days=21)
    due_date = parse_iso_date(project.get('due_date'), default_due)
    if due_date < datetime.now().date():
        due_date = datetime.now().date() + timedelta(days=3)

    stages = []
    cursor = due_date
    for template in reversed(stage_templates):
        duration = max(1, template['duration'])
        stage_end = cursor
        stage_start = cursor - timedelta(days=duration - 1)
        if stage_start > stage_end:
            stage_start = stage_end
        stages.append({
            'key': template['key'],
            'title': template['title'],
            'plan_start': stage_start,
            'plan_end': stage_end,
            'duration': duration
        })
        cursor = stage_start - timedelta(days=1)
    stages.reverse()

    stage_order = {stage['key']: idx for idx, stage in enumerate(stages)}
    status_stage_map = {
        '計画中': 'plan',
        '進行中': 'edit',
        'レビュー中': 'review',
        '納品待ち': 'delivery',
        '完了': 'delivery'
    }
    current_stage_key = status_stage_map.get(project.get('status'), 'edit')
    if project.get('delivered'):
        current_stage_key = 'delivery'
    current_index = stage_order.get(current_stage_key, 2)

    auto_tasks = []
    previous_task_id = None

    for idx, stage in enumerate(stages):
        task_id = project['id'] * 100 + (idx + 1)
        if project.get('delivered') or project.get('status') == '完了':
            status = '完了'
        elif idx < current_index:
            status = '完了'
        elif idx == current_index:
            status = 'レビュー中' if stage['key'] == 'review' and project.get('status') == 'レビュー中' else '進行中'
        else:
            status = '未着手'

        if status == '完了':
            progress = 100
        elif status == 'レビュー中':
            progress = 80
        elif status == '進行中':
            progress = 60
        else:
            progress = 0

        plan_start = isoformat_date(stage['plan_start'])
        plan_end = isoformat_date(stage['plan_end'])

        if status == '完了':
            actual_start = plan_start
            actual_end = plan_end
        elif status in {'レビュー中', '進行中'}:
            actual_start = plan_start
            actual_end = ''
        else:
            actual_start = ''
            actual_end = ''

        dependencies = []
        if previous_task_id:
            dependencies.append({'task_id': previous_task_id, 'type': 'FS'})

        task = {
            'id': task_id,
            'title': stage['title'],
            'project_id': project['id'],
            'project_name': project.get('name'),
            'company_name': company_name,
            'color': color,
            'type': 'AUTO',
            'status': status,
            'assignee': project.get('assignee', '未割当'),
            'priority': '高' if idx <= 2 else '中',
            'progress': progress,
            'due_date': plan_end,
            'plan_start': plan_start,
            'plan_end': plan_end,
            'actual_start': actual_start,
            'actual_end': actual_end,
            'order_index': idx + 1,
            'dependencies': dependencies,
            'created_by': 'システム',
            'updated_by': 'システム',
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'notes': f"{project.get('video_axis', 'LONG')} / {project.get('status', '-')}",
            'history': [],
            'task_origin': 'auto',
            'auto_stage': stage['key'],
            'auto_generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'user_modified': False
        }
        auto_tasks.append(task)
        previous_task_id = task_id

    return auto_tasks


def initialize_project_gantt_tasks(project: dict, company_name: str, company_id: int):
    project_id = project['id']
    project.setdefault('company_id', company_id)
    project.setdefault('company_name', company_name)
    project_color = ensure_project_color(company_id, project)
    ensure_project_status_history(project)
    project_tasks = PROJECT_GANTT_TASKS.setdefault(project_id, [])
    existing_auto = {task.get('auto_stage'): task for task in project_tasks if task.get('task_origin') == 'auto'}
    generated = build_auto_gantt_tasks(project, company_name, project_color)

    seen_stages = set()
    for auto_task in generated:
        stage = auto_task['auto_stage']
        seen_stages.add(stage)
        if stage in existing_auto:
            existing = existing_auto[stage]
            existing.update({
                'project_name': auto_task['project_name'],
                'company_name': auto_task['company_name'],
                'color': project_color,
                'plan_start': auto_task['plan_start'],
                'plan_end': auto_task['plan_end'],
                'due_date': auto_task['due_date'],
                'dependencies': auto_task['dependencies'],
                'order_index': auto_task['order_index'],
                'auto_generated_at': auto_task['auto_generated_at'],
                'assignee': auto_task['assignee']
            })
            if not existing.get('user_modified'):
                existing['status'] = auto_task['status']
                existing['progress'] = auto_task['progress']
                existing['actual_start'] = auto_task['actual_start']
                existing['actual_end'] = auto_task['actual_end']
            existing.setdefault('task_origin', 'auto')
            existing.setdefault('history', [])
        else:
            project_tasks.append(auto_task)

    project_tasks[:] = sorted(project_tasks, key=lambda t: (t.get('order_index') or 9999, t.get('id')))


def rebuild_task_cache():
    global TASK_CACHE
    tasks = []
    for project_id in sorted(PROJECT_GANTT_TASKS.keys()):
        for task in PROJECT_GANTT_TASKS[project_id]:
            tasks.append(copy.deepcopy(task))
    tasks.extend(copy.deepcopy(GENERAL_TASKS))
    TASK_CACHE = tasks


def get_all_tasks():
    if not TASK_CACHE:
        rebuild_task_cache()
    return copy.deepcopy(TASK_CACHE)


def gather_project_tasks():
    tasks = []
    for project_id, project_tasks in PROJECT_GANTT_TASKS.items():
        for task in project_tasks:
            tasks.append(copy.deepcopy(task))
    for task in GENERAL_TASKS:
        tasks.append(copy.deepcopy(task))
    return tasks


def get_project_tasks(project_id: int):
    tasks = PROJECT_GANTT_TASKS.get(project_id, [])
    return copy.deepcopy(sorted(tasks, key=lambda t: (t.get('order_index') or 9999, t.get('id'))))


def find_task_with_container(task_id: int):
    for project_id, tasks in PROJECT_GANTT_TASKS.items():
        for task in tasks:
            if task.get('id') == task_id:
                return task, tasks
    for task in GENERAL_TASKS:
        if task.get('id') == task_id:
            return task, GENERAL_TASKS
    return None, None


def initialize_all_project_tasks():
    PROJECT_COLOR_ASSIGNMENTS.clear()
    for company in SAMPLE_COMPANIES:
        for project in company['projects']:
            project.setdefault('company_id', company['id'])
            initialize_project_gantt_tasks(project, company['name'], company['id'])
    rebuild_task_cache()


def next_task_id():
    return next(TASK_ID_COUNTER)


def next_asset_id():
    return max([a['id'] for a in SAMPLE_ASSETS], default=0) + 1


def create_task_entry(
    title: str,
    task_type: str = 'EDIT',
    status: str = '待機中',
    assignee: str = 'テスト',
    due_date: str = '',
    priority: str = '中',
    project=None,
    project_id: int = None,
    progress: int = 0,
    plan_start: str = '',
    plan_end: str = '',
    actual_start: str = '',
    actual_end: str = '',
    order_index: int = None,
    dependencies=None,
    created_by: str = None,
    updated_by: str = None,
    notes: str = '',
    company_id: int = None,
    company_name: str = None,
    project_color: str = None,
    origin: str = 'manual'
):
    project_name = ''
    if project:
        project_name = project.get('name', '')
        project_id = project.get('id')
        company_id = company_id or project.get('company_id')
        company_name = company_name or project.get('company_name')
        project_color = project_color or project.get('color')
    task_type = (task_type or 'OTHER').upper()
    normalized_dependencies = []
    if dependencies:
        for dep in dependencies:
            if isinstance(dep, dict):
                task_id = dep.get('task_id')
                dep_type = (dep.get('type') or 'FS').upper()
            else:
                task_id = dep
                dep_type = 'FS'
            if task_id:
                normalized_dependencies.append({'task_id': int(task_id), 'type': dep_type})
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not plan_start and due_date:
        try:
            due_dt = datetime.strptime(due_date, '%Y-%m-%d')
            plan_start = (due_dt - timedelta(days=3)).strftime('%Y-%m-%d')
        except ValueError:
            plan_start = ''
    if not plan_end:
        plan_end = due_date or plan_start
    color = project_color
    if project_id and not color and company_id:
        project_color = ensure_project_color(company_id, project or {'id': project_id, 'company_id': company_id})
        color = project_color
    task = {
        'id': next_task_id(),
        'title': title,
        'project_name': project_name,
        'project_id': project_id,
        'company_name': company_name or (project or {}).get('company_name'),
        'color': color,
        'type': task_type,
        'status': status,
        'assignee': assignee,
        'due_date': due_date,
        'priority': priority,
        'progress': progress,
        'plan_start': plan_start,
        'plan_end': plan_end,
        'actual_start': actual_start,
        'actual_end': actual_end,
        'order_index': order_index,
        'dependencies': normalized_dependencies,
        'created_by': created_by or (g.current_user['name'] if getattr(g, 'current_user', None) else 'システム'),
        'updated_by': updated_by or (g.current_user['name'] if getattr(g, 'current_user', None) else 'システム'),
        'updated_at': now_str,
        'notes': notes,
        'history': [],
        'task_origin': origin,
        'user_modified': origin != 'auto'
    }
    return task


TASK_DEPENDENCY_TYPES = {'FS', 'SS', 'FF', 'SF'}


def find_task(task_id: int):
    task, _ = find_task_with_container(task_id)
    return task


def record_task_history(task: dict, field: str, old_value, new_value, actor: str):
    if old_value == new_value:
        return
    entry = {
        'id': len(task.setdefault('history', [])) + 1,
        'field': field,
        'old': old_value,
        'new': new_value,
        'actor': actor,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    task['history'].insert(0, entry)


def update_task_metadata(task: dict, actor: str):
    task['updated_by'] = actor
    task['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')


def parse_datetime_safe(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidates = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d'
        ]
        for fmt in candidates:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def record_project_status_change(project_id: int, new_status: str, actor: str = None, changed_at=None):
    if not new_status:
        return
    actor = actor or STATUS_HISTORY_DEFAULT_ACTOR
    history = PROJECT_STATUS_HISTORY.setdefault(project_id, [])

    if isinstance(changed_at, datetime):
        timestamp_dt = changed_at
    elif isinstance(changed_at, str):
        timestamp_dt = parse_datetime_safe(changed_at) or datetime.now()
    else:
        timestamp_dt = datetime.now()
    timestamp_str = timestamp_dt.strftime('%Y-%m-%d %H:%M')

    last_entry = history[-1] if history else None
    if last_entry and last_entry.get('status') == new_status:
        # 既存ステータスと同じ場合はタイムスタンプのみ更新
        last_entry['changed_at'] = timestamp_str
        last_entry['changed_by'] = actor
        return

    entry = {
        'status': new_status,
        'changed_at': timestamp_str,
        'changed_by': actor
    }
    history.append(entry)
    # 履歴を最新順に保つ（古いものから最大100件残す）
    if len(history) > 100:
        del history[:-100]


def ensure_project_status_history(project: dict, actor: str = STATUS_HISTORY_DEFAULT_ACTOR):
    project_id = project.get('id')
    if project_id is None:
        return []
    if PROJECT_STATUS_HISTORY.get(project_id):
        return PROJECT_STATUS_HISTORY[project_id]

    seed_timestamp = (
        project.get('created_at')
        or project.get('delivery_date')
        or project.get('due_date')
        or datetime.now()
    )
    seed_dt = parse_datetime_safe(seed_timestamp) or datetime.now()
    initial_status = project.get('status') or '進行中'
    record_project_status_change(project_id, initial_status, actor=actor, changed_at=seed_dt)
    return PROJECT_STATUS_HISTORY[project_id]


def get_project_status_history(project_id: int):
    history = PROJECT_STATUS_HISTORY.get(project_id, [])
    return [
        {
            'status': entry.get('status'),
            'changed_at': entry.get('changed_at'),
            'changed_by': entry.get('changed_by') or STATUS_HISTORY_DEFAULT_ACTOR
        }
        for entry in history
    ]


def build_project_status_timeline(project: dict):
    project_id = project.get('id')
    if project_id is None:
        return {'segments': [], 'days': [], 'start': None, 'end': None, 'history': []}

    history_entries = PROJECT_STATUS_HISTORY.get(project_id)
    if not history_entries:
        history_entries = ensure_project_status_history(project)

    events = []
    for entry in history_entries:
        dt = parse_datetime_safe(entry.get('changed_at')) or datetime.now()
        events.append({
            'status': entry.get('status'),
            'changed_at': dt,
            'changed_by': entry.get('changed_by') or STATUS_HISTORY_DEFAULT_ACTOR
        })

    if not events:
        now_dt = datetime.now()
        events.append({
            'status': project.get('status', '進行中'),
            'changed_at': now_dt,
            'changed_by': STATUS_HISTORY_DEFAULT_ACTOR
        })

    events.sort(key=lambda item: item['changed_at'])

    start_dt = events[0]['changed_at']
    end_candidates = [
        events[-1]['changed_at'],
        parse_datetime_safe(project.get('delivery_date')),
        parse_datetime_safe(project.get('due_date')),
        datetime.now()
    ]
    end_candidates = [dt for dt in end_candidates if dt is not None]
    end_dt = max(end_candidates) if end_candidates else datetime.now()

    max_span = timedelta(days=MAX_PROJECT_STATUS_TIMELINE_DAYS)
    if end_dt - start_dt > max_span:
        end_dt = start_dt + max_span

    segments = []
    for idx, event in enumerate(events):
        seg_start_dt = event['changed_at'].date()
        if idx + 1 < len(events):
            next_dt = events[idx + 1]['changed_at'].date() - timedelta(days=1)
        else:
            next_dt = end_dt.date()
        if next_dt < seg_start_dt:
            next_dt = seg_start_dt

        segments.append({
            'status': event['status'],
            'start_date': seg_start_dt.strftime('%Y-%m-%d'),
            'end_date': next_dt.strftime('%Y-%m-%d'),
            'changed_at': event['changed_at'].strftime('%Y-%m-%d %H:%M'),
            'changed_by': event.get('changed_by') or STATUS_HISTORY_DEFAULT_ACTOR
        })

    days = []
    for segment in segments:
        seg_start = parse_datetime_safe(segment['start_date'])
        seg_end = parse_datetime_safe(segment['end_date'])
        if not seg_start or not seg_end:
            continue
        current = seg_start
        while current <= seg_end:
            days.append({
                'date': current.strftime('%Y-%m-%d'),
                'status': segment['status'],
                'is_change': current == seg_start,
                'changed_by': segment.get('changed_by'),
                'changed_at': segment.get('changed_at')
            })
            current += timedelta(days=1)

    history_payload = [
        {
            'status': event['status'],
            'changed_at': event['changed_at'].strftime('%Y-%m-%d %H:%M'),
            'changed_by': event.get('changed_by') or STATUS_HISTORY_DEFAULT_ACTOR
        }
        for event in events
    ]

    return {
        'segments': segments,
        'days': days,
        'start': segments[0]['start_date'] if segments else None,
        'end': segments[-1]['end_date'] if segments else None,
        'history': history_payload
    }


STATUS_BADGE_CLASS_MAP = {
    '完了': 'is-complete',
    '納品済': 'is-complete',
    '納品待ち': 'is-delivery',
    'レビュー中': 'is-review',
    '確認待ち': 'is-review',
    '進行中': 'is-progress',
    '計画中': 'is-planning',
    '制作中': 'is-planning',
    '期限超過': 'is-danger',
    '遅延': 'is-danger',
    '残り僅か': 'is-warning'
}


def get_status_badge_class(status: str) -> str:
    if not status:
        return 'is-default'
    normalized = str(status).strip().replace(' ', '')
    return STATUS_BADGE_CLASS_MAP.get(normalized, 'is-default')


def build_client_portal_context(current_user):
    all_projects = get_all_projects()
    today = datetime.now().date()
    assets_page_url = url_for('assets') if has_request_context() else '/assets'

    deliverables = []
    progress_entries = []
    alerts = {'due_soon': [], 'overdue': []}

    for project in all_projects:
        company_name = project.get('client_name') or project.get('company_name') or '未設定'
        company_id = project.get('company_id') or 0
        color = ensure_project_color(company_id, project)
        due_date = parse_iso_date(project.get('due_date'))
        delivery_date = parse_iso_date(project.get('delivery_date'))
        status = project.get('status') or '進行中'
        progress_value = project.get('progress') or 0
        delivered = bool(project.get('delivered'))
        days_to_due = (due_date - today).days if due_date else None

        timeline = build_project_status_timeline(project)
        recent_history = list(reversed(timeline.get('history', [])[-4:]))

        progress_entry = {
            'project_id': project.get('id'),
            'project_name': project.get('name'),
            'company_name': company_name,
            'color': color,
            'status': status,
            'status_class': get_status_badge_class(status),
            'progress': progress_value,
            'due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
            'delivery_date': delivery_date.strftime('%Y-%m-%d') if delivery_date else '',
            'days_to_due': days_to_due,
            'delivered': delivered,
            'recent_history': recent_history,
            'timeline': timeline
        }
        progress_entries.append(progress_entry)

        if days_to_due is not None and not delivered:
            if days_to_due < 0:
                alerts['overdue'].append(progress_entry)
            elif days_to_due <= 5:
                alerts['due_soon'].append(progress_entry)

        final_assets = [
            {
                'id': asset.get('id'),
                'name': asset.get('name'),
                'size': asset.get('size'),
                'version': asset.get('version'),
                'uploaded_at': asset.get('uploaded_at'),
                'download_url': asset.get('url') or assets_page_url
            }
            for asset in SAMPLE_ASSETS
            if asset.get('project_name') == project.get('name')
            and str(asset.get('kind', '')).lower() in CLIENT_FINAL_ASSET_KINDS
        ]

        if delivered or final_assets:
            approval_label = '納品済' if delivered else ('確認待ち' if status in {'レビュー中', '納品待ち'} else '制作中')
            deliverables.append({
                'project_id': project.get('id'),
                'project_name': project.get('name'),
                'company_name': company_name,
                'approval_label': approval_label,
                'badge_class': get_status_badge_class(approval_label),
                'delivery_date': delivery_date.strftime('%Y-%m-%d') if delivery_date else '',
                'due_date': due_date.strftime('%Y-%m-%d') if due_date else '',
                'days_to_due': days_to_due,
                'progress': progress_value,
                'delivered': delivered,
                'color': color,
                'assets': final_assets
            })

    deliverables.sort(key=lambda item: item.get('delivery_date') or item.get('due_date') or '0000-00-00', reverse=True)
    progress_entries.sort(key=lambda item: (
        item.get('delivered', False),
        item.get('due_date') or '9999-12-31',
        item.get('project_name') or ''
    ))

    summary = {
        'total_projects': len(all_projects),
        'active_projects': len([p for p in all_projects if p.get('status') in {'進行中', 'レビュー中', '納品待ち'}]),
        'delivered_projects': len([p for p in all_projects if p.get('delivered') or p.get('status') == '完了']),
        'review_projects': len([p for p in all_projects if p.get('status') in {'レビュー中', '納品待ち'}]),
        'delivery_ready': len(deliverables),
        'due_soon_count': len(alerts['due_soon']),
        'overdue_count': len(alerts['overdue'])
    }

    return {
        'summary': summary,
        'deliverables': deliverables,
        'progress_entries': progress_entries,
        'alerts': alerts,
        'today_label': today.strftime('%Y-%m-%d'),
        'portal_profile': ensure_client_portal_profile(current_user) if current_user else None
    }


def serialize_gantt_task(task: dict):
    dependencies = task.get('dependencies', [])
    dependencies_string = ",".join(str(dep.get('task_id')) for dep in dependencies if dep.get('task_id'))
    return {
        'id': task.get('id'),
        'name': task.get('title'),
        'title': task.get('title'),
        'project_id': task.get('project_id'),
        'project_name': task.get('project_name'),
        'company_name': task.get('company_name'),
        'auto_stage': task.get('auto_stage'),
        'assignee': task.get('assignee'),
        'status': task.get('status'),
        'priority': task.get('priority'),
        'type': task.get('type'),
        'progress': int(task.get('progress', 0) or 0),
        'plan_start': task.get('plan_start'),
        'plan_end': task.get('plan_end'),
        'actual_start': task.get('actual_start'),
        'actual_end': task.get('actual_end'),
        'due_date': task.get('due_date'),
        'order_index': task.get('order_index'),
        'dependencies': dependencies,
        'dependencies_string': dependencies_string,
        'notes': task.get('notes', ''),
        'updated_at': task.get('updated_at'),
        'updated_by': task.get('updated_by'),
        'created_by': task.get('created_by'),
        'history': task.get('history', [])[:10],  # 最新10件まで
        'task_origin': task.get('task_origin', 'manual')
    }


def filter_tasks_for_user(tasks: list, current_user: dict):
    if not current_user:
        return []
    role = current_user.get('role')
    if role == 'admin':
        return tasks
    if role == 'editor':
        user_name = current_user.get('name')
        return [task for task in tasks if task.get('assignee') == user_name]
    # その他ロールは閲覧のみ想定
    return tasks


def filter_tasks_by_params(tasks: list, params: dict):
    filtered = tasks
    project_id = params.get('project_id')
    if project_id:
        filtered = [task for task in filtered if str(task.get('project_id')) == str(project_id)]

    assignee = params.get('assignee')
    if assignee:
        filtered = [task for task in filtered if task.get('assignee') == assignee]

    status = params.get('status')
    if status:
        filtered = [task for task in filtered if task.get('status') == status]

    keyword = params.get('keyword')
    if keyword:
        keyword_lower = keyword.lower()
        filtered = [
            task for task in filtered
            if keyword_lower in (task.get('title') or '').lower()
            or keyword_lower in (task.get('notes') or '').lower()
            or keyword_lower in (task.get('project_name') or '').lower()
        ]

    start_date = params.get('start_date')
    end_date = params.get('end_date')
    if start_date:
        filtered = [
            task for task in filtered
            if (task.get('plan_end') and task['plan_end'] >= start_date) or not task.get('plan_end')
        ]
    if end_date:
        filtered = [
            task for task in filtered
            if (task.get('plan_start') and task['plan_start'] <= end_date) or not task.get('plan_start')
        ]

    return sorted(filtered, key=lambda t: (t.get('order_index') or 9999, t.get('id')))


def collect_task_filters(tasks: list):
    assignees = sorted({task.get('assignee') for task in tasks if task.get('assignee')})
    statuses = sorted({task.get('status') for task in tasks if task.get('status')})
    projects = sorted(
        {
            (task.get('project_id'), task.get('project_name'))
            for task in tasks
            if task.get('project_id') and task.get('project_name')
        },
        key=lambda item: item[1]
    )
    return {
        'assignees': assignees,
        'statuses': statuses,
        'projects': [{'id': pid, 'name': pname} for pid, pname in projects]
    }


def summarize_projects_for_gantt() -> list[dict]:
    summary = []

    def normalize_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return None

    for company in SAMPLE_COMPANIES:
        company_id = company['id']
        for project in company['projects']:
            project_id = project['id']
            initialize_project_gantt_tasks(project, company['name'], company_id)
            color = ensure_project_color(company_id, project)
            tasks = PROJECT_GANTT_TASKS.get(project_id, [])
            manual_tasks = [task for task in GENERAL_TASKS if task.get('project_id') == project_id]
            combined = list(tasks) + manual_tasks

            entry = {
                'project_id': project_id,
                'project_name': project.get('name'),
                'company_name': company['name'],
                'color': color,
                'assignee': project.get('assignee', ''),
                'phases': [],
                'range': {'plan_start': None, 'plan_end': None, 'timeline_start': None, 'timeline_end': None}
            }

            for index, task in enumerate(sorted(combined, key=lambda t: (t.get('order_index') or (index + 1), t.get('plan_start') or ''))):
                plan_start = task.get('plan_start') or task.get('actual_start') or project.get('due_date') or task.get('due_date')
                plan_end = task.get('plan_end') or task.get('actual_end') or project.get('due_date') or plan_start
                actual_start = task.get('actual_start')
                actual_end = task.get('actual_end') or (project.get('delivery_date') if task.get('status') == '完了' else '')

                if not plan_start:
                    plan_start = datetime.now().strftime('%Y-%m-%d')
                if not plan_end:
                    plan_end = plan_start

                entry['phases'].append({
                    'title': task.get('title'),
                    'status': task.get('status'),
                    'plan_start': plan_start,
                    'plan_end': plan_end,
                    'actual_start': actual_start,
                    'actual_end': actual_end,
                    'origin': task.get('task_origin', 'manual'),
                    'auto_stage': task.get('auto_stage'),
                    'order_index': task.get('order_index') or (index + 1)
                })

                start_dt = normalize_date(plan_start) or normalize_date(actual_start)
                end_dt = normalize_date(plan_end) or normalize_date(actual_end) or start_dt
                if start_dt:
                    current_start = entry['range']['plan_start']
                    if current_start is None or start_dt < current_start:
                        entry['range']['plan_start'] = start_dt
                if end_dt:
                    current_end = entry['range']['plan_end']
                    if current_end is None or end_dt > current_end:
                        entry['range']['plan_end'] = end_dt

            timeline_info = build_project_status_timeline(project)
            entry['status_timeline'] = timeline_info['segments']
            entry['status_days'] = timeline_info['days']
            entry['status_history'] = timeline_info['history']

            timeline_start_dt = normalize_date(timeline_info['start'])
            timeline_end_dt = normalize_date(timeline_info['end'])

            if timeline_start_dt:
                entry['range']['timeline_start'] = timeline_start_dt
                current_start = entry['range']['plan_start']
                if current_start is None or timeline_start_dt < current_start:
                    entry['range']['plan_start'] = timeline_start_dt
            if timeline_end_dt:
                entry['range']['timeline_end'] = timeline_end_dt
                current_end = entry['range']['plan_end']
                if current_end is None or timeline_end_dt > current_end:
                    entry['range']['plan_end'] = timeline_end_dt

            if entry['range']['plan_start'] is not None:
                entry['range']['plan_start'] = entry['range']['plan_start'].strftime('%Y-%m-%d')
            if entry['range']['plan_end'] is not None:
                entry['range']['plan_end'] = entry['range']['plan_end'].strftime('%Y-%m-%d')
            if entry['range']['timeline_start'] is not None:
                entry['range']['timeline_start'] = entry['range']['timeline_start'].strftime('%Y-%m-%d')
            if entry['range']['timeline_end'] is not None:
                entry['range']['timeline_end'] = entry['range']['timeline_end'].strftime('%Y-%m-%d')

            summary.append(entry)

    summary.sort(key=lambda item: (item.get('company_name') or '', item.get('project_name') or ''))
    return summary


def parse_date_safe(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def filter_project_summary_entries(summary: list[dict], params: dict, filtered_tasks: list[dict]):
    project_ids_from_tasks = {task.get('project_id') for task in filtered_tasks if task.get('project_id')}
    project_filter = (params.get('project_id') or '').strip()
    assignee_filter = (params.get('assignee') or '').strip()
    status_filter = (params.get('status') or '').strip()
    keyword_filter = (params.get('keyword') or '').strip().lower()
    start_filter = parse_date_safe(params.get('start_date'))
    end_filter = parse_date_safe(params.get('end_date'))

    def entry_matches(entry):
        if project_filter and str(entry.get('project_id')) != project_filter:
            return False

        if assignee_filter:
            entry_assignee = entry.get('assignee') or ''
            phase_assignees = {
                phase.get('assignee')
                for phase in entry.get('phases', [])
                if phase.get('assignee')
            }
            if assignee_filter != entry_assignee and assignee_filter not in phase_assignees:
                return False

        if status_filter:
            status_set = {
                segment.get('status')
                for segment in entry.get('status_timeline', [])
                if segment.get('status')
            }
            status_set.update({
                phase.get('status')
                for phase in entry.get('phases', [])
                if phase.get('status')
            })
            if status_filter not in status_set:
                return False

        if keyword_filter:
            project_label = (entry.get('project_name') or '').lower()
            company_label = (entry.get('company_name') or '').lower()
            if keyword_filter not in project_label and keyword_filter not in company_label:
                return False

        entry_start = parse_date_safe(entry.get('range', {}).get('timeline_start') or entry.get('range', {}).get('plan_start'))
        entry_end = parse_date_safe(entry.get('range', {}).get('timeline_end') or entry.get('range', {}).get('plan_end'))
        if start_filter and entry_end and entry_end < start_filter:
            return False
        if end_filter and entry_start and entry_start > end_filter:
            return False
        return True

    results = []
    for entry in summary:
        if project_filter and str(entry.get('project_id')) != project_filter:
            continue
        if project_ids_from_tasks and entry.get('project_id') not in project_ids_from_tasks:
            continue
        if not entry_matches(entry):
            continue
        results.append(entry)

    if not results and project_filter:
        # Fallback: show the requested project even if task filters narrowed everything out
        results = [
            entry for entry in summary
            if str(entry.get('project_id')) == project_filter
        ]
    return results


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
PROJECT_NAME_TO_ID = {project['name']: project['id'] for project in SAMPLE_PROJECTS}

for asset in SAMPLE_ASSETS:
    if not asset.get('project_id'):
        asset['project_id'] = PROJECT_NAME_TO_ID.get(asset.get('project_name'))


def find_project_by_id(project_id: int):
    for company in SAMPLE_COMPANIES:
        for project in company['projects']:
            if project['id'] == project_id:
                return project, company
    return None, None


def ensure_video_items(project_id: int, project: dict = None):
    if project_id not in PROJECT_VIDEO_ITEMS:
        if project is None:
            project, _ = find_project_by_id(project_id)
        assignee = project.get('assignee', 'テスト') if project else 'テスト'
        due_date = project.get('due_date', '')
        defaults = [
            {
                'id': next(VIDEO_ITEM_ID_COUNTER),
                'axis': 'LONG',
                'title': '長尺動画',
                'status': '進行中',
                'assignee': assignee,
                'planned_start': due_date,
                'planned_end': due_date
            },
            {
                'id': next(VIDEO_ITEM_ID_COUNTER),
                'axis': 'SHORT',
                'title': 'ショート動画',
                'status': '計画中',
                'assignee': assignee,
                'planned_start': due_date,
                'planned_end': due_date
            }
        ]
        PROJECT_VIDEO_ITEMS[project_id] = defaults
    return PROJECT_VIDEO_ITEMS[project_id]


def ensure_project_comments(project_id: int):
    if project_id not in PROJECT_COMMENTS:
        PROJECT_COMMENTS[project_id] = [
            {
                'id': next(COMMENT_ID_COUNTER),
                'author': 'テスト',
                'content': '素材の確認をお願いします。',
                'created_at': '2025-04-01 10:00'
            },
            {
                'id': next(COMMENT_ID_COUNTER),
                'author': 'テスト',
                'content': '編集作業を開始しました。',
                'created_at': '2025-04-02 14:30'
            }
        ]
    return PROJECT_COMMENTS[project_id]


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
    all_tasks = get_all_tasks()
    total_tasks = len(all_tasks)
    active_tasks = len([t for t in all_tasks if t['status'] in ['進行中', '待機中', 'レビュー中']])
    completed_tasks = len([t for t in all_tasks if t['status'] == '完了'])
    pending_tasks = len([t for t in all_tasks if t['status'] in ['未着手', '待機中']])
    
    # 最近のタスク（優先度順、期限順）
    recent_tasks = sorted(
        all_tasks,
        key=lambda x: (
            0 if x.get('priority') == '高' else 1,
            x.get('due_date') or ''
        )
    )[:5]
    
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
    
    return render_template('index.html', stats=stats, company_stats=company_stats, recent_projects=all_projects[:5], recent_tasks=recent_tasks, task_type_labels=TASK_TYPE_LABELS)

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

    company_id = company['id'] if company else project.get('company_id')
    initialize_project_gantt_tasks(project, company['name'] if company else project.get('company'), company_id)
    project_tasks = get_project_tasks(project_id)

    video_items = copy.deepcopy(ensure_video_items(project_id, project))

    comments = copy.deepcopy(ensure_project_comments(project_id))

    history = [
        {'id': 1, 'action': '案件作成', 'user': 'テスト', 'timestamp': '2025-03-15 09:00'},
        {'id': 2, 'action': 'ステータス変更: 計画中 → 進行中', 'user': 'テスト', 'timestamp': '2025-03-20 10:30'},
        {'id': 3, 'action': '担当者変更', 'user': 'テスト', 'timestamp': '2025-04-01 11:00'},
    ]

    project_assets = [a for a in SAMPLE_ASSETS if a.get('project_id') == project_id]
    if not project_assets:
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
        task_type_labels=TASK_TYPE_LABELS,
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


@app.route('/api/projects/<int:project_id>/status-history')
@login_required
def api_project_status_history(project_id):
    project, _ = find_project_by_id(project_id)
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404
    history = get_project_status_history(project_id)
    return jsonify({
        'status': 'success',
        'data': history
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
    actor = g.current_user['name'] if g.current_user and g.current_user.get('name') else STATUS_HISTORY_DEFAULT_ACTOR
    previous_status = project.get('status')
    
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

    if company:
        initialize_project_gantt_tasks(project, company['name'], company['id'])
        rebuild_task_cache()
    
    # 案件名が変更された場合、関連するタスクの案件名も更新
    if old_project_name and new_project_name != old_project_name:
        for task in PROJECT_GANTT_TASKS.get(project_id, []):
            task['project_name'] = new_project_name
        for manual_task in GENERAL_TASKS:
            if manual_task.get('project_id') == project_id:
                manual_task['project_name'] = new_project_name
        rebuild_task_cache()
    
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

    global SAMPLE_PROJECTS, PROJECT_NAME_TO_ID
    SAMPLE_PROJECTS = get_all_projects()
    PROJECT_NAME_TO_ID = {proj['name']: proj['id'] for proj in SAMPLE_PROJECTS}

    if previous_status != project.get('status'):
        record_project_status_change(project_id, project.get('status'), actor=actor)
    
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
    new_project['company_id'] = company_id
    company['projects'].append(new_project)
    actor = g.current_user['name'] if g.current_user and g.current_user.get('name') else STATUS_HISTORY_DEFAULT_ACTOR
    record_project_status_change(new_project['id'], new_project.get('status', '進行中'), actor=actor)
    initialize_project_gantt_tasks(new_project, company['name'], company_id)
    rebuild_task_cache()
    global SAMPLE_PROJECTS, PROJECT_NAME_TO_ID
    SAMPLE_PROJECTS = get_all_projects()
    PROJECT_NAME_TO_ID = {project['name']: project['id'] for project in SAMPLE_PROJECTS}
    
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
    actor = g.current_user['name'] if g.current_user and g.current_user.get('name') else STATUS_HISTORY_DEFAULT_ACTOR
    
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
    previous_status = project.get('status')
    
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
    
    status_changed = previous_status != project.get('status')
    if status_changed:
        changed_at = datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M') if delivered else datetime.now().strftime('%Y-%m-%d %H:%M')
        record_project_status_change(project_id, project.get('status'), actor=actor, changed_at=changed_at)

    if company:
        initialize_project_gantt_tasks(project, company['name'], company['id'])
        rebuild_task_cache()
    
    return jsonify({
        'status': 'success',
        'message': 'CL状態を更新しました',
        'data': {
            'delivered': delivered,
            'delivery_date': project.get('delivery_date', '')
        }
    })


@app.route('/api/projects/<int:project_id>/video-items', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_add_video_item(project_id):
    project, company = find_project_by_id(project_id)
    company_name = company['name'] if company else None
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'status': 'error', 'message': 'タイトルは必須です'}), 400

    axis = (data.get('axis') or 'LONG').upper()
    if axis not in {'LONG', 'SHORT'}:
        axis = 'LONG'

    items = ensure_video_items(project_id, project)
    item = {
        'id': next(VIDEO_ITEM_ID_COUNTER),
        'axis': axis,
        'title': title,
        'status': data.get('status', '進行中'),
        'assignee': data.get('assignee', project.get('assignee', '未割当')),
        'planned_start': data.get('planned_start', ''),
        'planned_end': data.get('planned_end', '')
    }
    items.append(item)

    return jsonify({'status': 'success', 'message': '動画アイテムを追加しました', 'data': item})


@app.route('/api/projects/<int:project_id>/tasks', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_add_project_task(project_id):
    project, company = find_project_by_id(project_id)
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'status': 'error', 'message': 'タスク名は必須です'}), 400
    company_name = company['name'] if company else None
    if company_name:
        project.setdefault('company_name', company_name)
        project.setdefault('company_id', company['id'])

    task = create_task_entry(
        title=title,
        task_type=data.get('type', 'EDIT'),
        status=data.get('status', '待機中'),
        assignee=data.get('assignee', project.get('assignee', '未割当')),
        due_date=data.get('due_date', ''),
        priority=data.get('priority', '中'),
        project=project,
        project_id=project_id,
        progress=int(data.get('progress', 0) or 0),
        plan_start=data.get('plan_start', ''),
        plan_end=data.get('plan_end', ''),
        actual_start=data.get('actual_start', ''),
        actual_end=data.get('actual_end', ''),
        dependencies=data.get('dependencies'),
        notes=data.get('notes', ''),
        company_id=company['id'] if company else project.get('company_id'),
        company_name=company_name,
        project_color=project.get('color'),
        origin='manual'
    )
    project_tasks = PROJECT_GANTT_TASKS.setdefault(project_id, [])
    if company_name:
        task['company_name'] = company_name
    if not task.get('order_index'):
        task['order_index'] = len(project_tasks) + 1
    project_tasks.append(task)
    project_tasks.sort(key=lambda t: (t.get('order_index') or 9999, t.get('id')))
    rebuild_task_cache()

    return jsonify({'status': 'success', 'message': 'タスクを追加しました', 'data': task})


@app.route('/api/projects/<int:project_id>/assets', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_add_project_asset(project_id):
    project, _ = find_project_by_id(project_id)
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'ファイル名は必須です'}), 400

    asset = {
        'id': next_asset_id(),
        'name': name,
        'project_name': project.get('name'),
        'project_id': project_id,
        'kind': data.get('kind', 'other'),
        'size': data.get('size', ''),
        'version': data.get('version', 1),
        'uploaded_by': g.current_user['name'] if g.current_user else 'システム',
        'uploaded_at': datetime.now().strftime('%Y-%m-%d'),
        'url': data.get('url', '')
    }
    SAMPLE_ASSETS.append(asset)

    return jsonify({'status': 'success', 'message': '素材を追加しました', 'data': asset})


@app.route('/api/projects/<int:project_id>/comments', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_add_project_comment(project_id):
    project, _ = find_project_by_id(project_id)
    if not project:
        return jsonify({'status': 'error', 'message': '案件が見つかりません'}), 404

    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'status': 'error', 'message': 'コメント内容を入力してください'}), 400

    comments = ensure_project_comments(project_id)
    comment = {
        'id': next(COMMENT_ID_COUNTER),
        'author': g.current_user['name'] if g.current_user else 'システム',
        'content': content,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    comments.append(comment)

    return jsonify({'status': 'success', 'message': 'コメントを追加しました', 'data': comment})

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
    my_tasks = get_all_tasks()
    
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
    my_tasks = get_all_tasks()  # 将来的には、自分のタスクのみをフィルタリング
    
    # 今日の日付を取得（期限超過の判定用）
    from datetime import date
    today = date.today().isoformat()
    
    # ページネーション用のパラメータ（将来実装）
    # 現在は全件表示だが、1画面10件表示に対応
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    return render_template('tasks.html', tasks=my_tasks, today=today, page=page, per_page=per_page, task_type_labels=TASK_TYPE_LABELS)

@app.route('/api/tasks')
def api_tasks():
    """タスク一覧API"""
    return jsonify({
        'status': 'success',
        'data': get_all_tasks()
    })

@app.route('/api/tasks/<int:task_id>')
def api_task_detail(task_id):
    """タスク詳細API"""
    task = find_task(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'タスクが見つかりません'}), 404
    
    return jsonify({
        'status': 'success',
        'data': task
    })


@app.route('/api/gantt/tasks')
@login_required
def api_gantt_tasks():
    current_user = g.current_user
    base_tasks = gather_project_tasks()
    user_tasks = filter_tasks_for_user(base_tasks, current_user)

    params = {
        'project_id': request.args.get('project_id'),
        'assignee': request.args.get('assignee'),
        'status': request.args.get('status'),
        'keyword': request.args.get('keyword'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
    }

    filtered_tasks = filter_tasks_by_params(user_tasks, params)
    include_history = request.args.get('include_history') == '1'

    def serialize(task):
        payload = serialize_gantt_task(task)
        if not include_history:
            payload.pop('history', None)
        return payload

    filters = collect_task_filters(user_tasks)

    all_tasks_payload = [serialize_gantt_task(task) for task in user_tasks]
    if not include_history:
        for entry in all_tasks_payload:
            entry.pop('history', None)

    project_summary = summarize_projects_for_gantt()

    return jsonify({
        'status': 'success',
        'data': [serialize(task) for task in filtered_tasks],
        'meta': {
            'filters': filters,
            'view': request.args.get('view', 'plan'),
            'total': len(filtered_tasks),
            'all_tasks': all_tasks_payload,
            'projects_summary': project_summary
        }
    })


@app.route('/api/gantt/tasks/<int:task_id>/history')
@login_required
def api_gantt_task_history(task_id):
    task = find_task(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'タスクが見つかりません'}), 404
    return jsonify({
        'status': 'success',
        'data': task.get('history', [])
    })


@app.route('/api/gantt/tasks/reorder', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_gantt_reorder():
    data = request.get_json() or {}
    order = data.get('order', [])
    if not isinstance(order, list):
        return jsonify({'status': 'error', 'message': 'orderはリスト形式で指定してください'}), 400

    actor = g.current_user['name'] if g.current_user else 'システム'
    updated = []
    affected_containers = set()
    for index, task_id in enumerate(order, start=1):
        task, container = find_task_with_container(task_id)
        if not task:
            continue
        record_task_history(task, 'order_index', task.get('order_index'), index, actor)
        task['order_index'] = index
        update_task_metadata(task, actor)
        updated.append(task_id)
        if container is not None:
            affected_containers.add(id(container))

    for project_id, tasks in PROJECT_GANTT_TASKS.items():
        tasks.sort(key=lambda t: (t.get('order_index') or 9999, t.get('id')))
    GENERAL_TASKS.sort(key=lambda t: (t.get('due_date') or '', t.get('id')))
    rebuild_task_cache()

    return jsonify({
        'status': 'success',
        'message': '表示順を更新しました',
        'data': {'updated_ids': updated}
    })

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
@role_required('admin', 'editor')
def api_update_task(task_id):
    """タスク更新API"""
    data = request.get_json() or {}
    task, container = find_task_with_container(task_id)
    
    if not task:
        return jsonify({'status': 'error', 'message': 'タスクが見つかりません'}), 404
    
    actor = g.current_user['name'] if g.current_user else 'システム'

    updatable_fields = [
        'title', 'type', 'status', 'assignee', 'due_date', 'priority',
        'progress', 'plan_start', 'plan_end', 'actual_start', 'actual_end',
        'order_index', 'notes'
    ]

    for field in updatable_fields:
        if field in data:
            value = data[field]
            if field == 'progress' and value is not None:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = task.get(field, 0)
            if field == 'order_index' and value is not None:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = task.get(field)
            record_task_history(task, field, task.get(field), value, actor)
            task[field] = value

    if 'project_id' in data or 'project_name' in data:
        new_project_id = data.get('project_id', task.get('project_id'))
        new_project_name = data.get('project_name')
        project = None
        company_name = None
        project_color = task.get('color')
        if new_project_id:
            project, company = find_project_by_id(int(new_project_id))
            if not project:
                return jsonify({'status': 'error', 'message': '対象の案件が見つかりません'}), 404
            new_project_name = project.get('name')
            company_name = company['name'] if company else None
            company_id = company['id'] if company else project.get('company_id')
            if company_id:
                project_color = ensure_project_color(company_id, project)
        elif new_project_name:
            new_project_id = PROJECT_NAME_TO_ID.get(new_project_name)
            if new_project_id:
                project, company = find_project_by_id(new_project_id)
                company_name = company['name'] if company else None
                company_id = company['id'] if company else project.get('company_id')
                if company_id and project:
                    project_color = ensure_project_color(company_id, project)
        record_task_history(task, 'project_id', task.get('project_id'), new_project_id, actor)
        record_task_history(task, 'project_name', task.get('project_name'), new_project_name, actor)

        if container is GENERAL_TASKS and new_project_id:
            GENERAL_TASKS.remove(task)
            container = PROJECT_GANTT_TASKS.setdefault(new_project_id, [])
            if not task.get('order_index'):
                task['order_index'] = len(container) + 1
            container.append(task)
        elif container is not GENERAL_TASKS and new_project_id and task.get('project_id') != new_project_id:
            # move between project lists
            if container:
                container.remove(task)
            destination = PROJECT_GANTT_TASKS.setdefault(new_project_id, [])
            destination.append(task)
            container = destination

        task['project_id'] = new_project_id
        task['project_name'] = new_project_name
        if company_name:
            task['company_name'] = company_name
        if project_color:
            task['color'] = project_color

    if 'dependencies' in data:
        deps_payload = data['dependencies'] or []
        normalized = []
        for dep in deps_payload:
            if isinstance(dep, dict):
                dep_id = dep.get('task_id')
                dep_type = (dep.get('type') or 'FS').upper()
            else:
                dep_id = dep
                dep_type = 'FS'
            if not dep_id or dep_id == task_id:
                continue
            if dep_type not in TASK_DEPENDENCY_TYPES:
                dep_type = 'FS'
            normalized.append({'task_id': int(dep_id), 'type': dep_type})
        record_task_history(task, 'dependencies', task.get('dependencies', []), normalized, actor)
        task['dependencies'] = normalized

    update_task_metadata(task, actor)
    if task.get('task_origin') == 'auto':
        task['user_modified'] = True

    for project_id, tasks in PROJECT_GANTT_TASKS.items():
        tasks.sort(key=lambda t: (t.get('order_index') or 9999, t.get('id')))
    GENERAL_TASKS.sort(key=lambda t: (t.get('due_date') or '', t.get('id')))
    rebuild_task_cache()
    
    return jsonify({
        'status': 'success',
        'message': 'タスクを更新しました',
        'data': task
    })

@app.route('/api/tasks', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_create_task():
    """タスク作成API"""
    data = request.get_json() or {}
    
    # バリデーション
    if not data.get('title'):
        return jsonify({'status': 'error', 'message': 'タスク名は必須です'}), 400
    
    project_id = data.get('project_id')
    project = None
    company = None
    company_name = None
    if project_id:
        project, company = find_project_by_id(project_id)
        if not project:
            return jsonify({'status': 'error', 'message': '対象の案件が見つかりません'}), 404
        if company:
            project.setdefault('company_name', company['name'])
            project.setdefault('company_id', company['id'])
        data['project_name'] = project.get('name')
        company_name = company['name'] if company else None
    else:
        project_name = data.get('project_name')
        if project_name:
            project_id = PROJECT_NAME_TO_ID.get(project_name)
            if project_id:
                project, company = find_project_by_id(project_id)
                if project:
                    company_name = company['name'] if company else None

    new_task = create_task_entry(
        title=data.get('title'),
        task_type=data.get('type', 'EDIT'),
        status=data.get('status', '待機中'),
        assignee=data.get('assignee', 'テスト'),
        due_date=data.get('due_date', ''),
        priority=data.get('priority', '中'),
        project=project,
        project_id=project_id,
        progress=int(data.get('progress', 0) or 0),
        plan_start=data.get('plan_start', ''),
        plan_end=data.get('plan_end', ''),
        actual_start=data.get('actual_start', ''),
        actual_end=data.get('actual_end', ''),
        order_index=data.get('order_index'),
        dependencies=data.get('dependencies'),
        notes=data.get('notes', ''),
        company_id=company['id'] if company else None,
        company_name=company_name,
        project_color=project.get('color') if project else None
    )

    if project_id:
        project_tasks = PROJECT_GANTT_TASKS.setdefault(project_id, [])
        if project and project_id and company_name:
            new_task['company_name'] = company_name
        if not new_task.get('order_index'):
            new_task['order_index'] = len(project_tasks) + 1
        project_tasks.append(new_task)
        project_tasks.sort(key=lambda t: (t.get('order_index') or 9999, t.get('id')))
    else:
        GENERAL_TASKS.append(new_task)
    rebuild_task_cache()
    
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


def get_next_invoice_id():
    return next(FINANCE_INVOICE_ID_COUNTER)


def get_next_payout_id():
    return next(FINANCE_PAYOUT_ID_COUNTER)


def serialize_invoice(invoice: dict) -> dict:
    return {
        'id': invoice['id'],
        'project_name': invoice['project_name'],
        'amount': invoice['amount'],
        'issue_date': invoice.get('issue_date', ''),
        'status': invoice['status'],
        'status_label': FINANCE_INVOICE_STATUS_LABELS.get(invoice['status'], invoice['status'])
    }


def serialize_payout(payout: dict) -> dict:
    return {
        'id': payout['id'],
        'editor': payout['editor'],
        'project_name': payout['project_name'],
        'amount': payout['amount'],
        'status': payout['status'],
        'status_label': FINANCE_PAYOUT_STATUS_LABELS.get(payout['status'], payout['status'])
    }


def calculate_finance_summary():
    total_revenue = sum(invoice.get('amount', 0) or 0 for invoice in FINANCE_INVOICES)
    total_cost = sum(payout.get('amount', 0) or 0 for payout in FINANCE_PAYOUTS)
    profit = total_revenue - total_cost
    profit_rate = round((profit / total_revenue * 100), 1) if total_revenue else 0
    return {
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'profit': profit,
        'profit_rate': profit_rate
    }


def ensure_reportlab_font():
    global REPORT_PDF_FONT_REGISTERED
    if not REPORTLAB_AVAILABLE or REPORT_PDF_FONT_REGISTERED:
        return
    pdfmetrics.registerFont(UnicodeCIDFont(REPORT_PDF_FONT_NAME))
    REPORT_PDF_FONT_REGISTERED = True


def gather_finance_report_data():
    summary = calculate_finance_summary()
    invoices = [serialize_invoice(invoice) for invoice in FINANCE_INVOICES]
    payouts = [serialize_payout(payout) for payout in FINANCE_PAYOUTS]

    invoice_by_status = {}
    for invoice in invoices:
        invoice_by_status.setdefault(invoice['status_label'], {
            'count': 0,
            'total': 0
        })
        invoice_by_status[invoice['status_label']]['count'] += 1
        invoice_by_status[invoice['status_label']]['total'] += invoice['amount']

    payout_by_status = {}
    for payout in payouts:
        payout_by_status.setdefault(payout['status_label'], {
            'count': 0,
            'total': 0
        })
        payout_by_status[payout['status_label']]['count'] += 1
        payout_by_status[payout['status_label']]['total'] += payout['amount']

    companies_summary = []
    for company in SAMPLE_COMPANIES:
        projects = company.get('projects', [])
        completed = len([p for p in projects if p.get('status') == '完了' or p.get('delivered')])
        in_progress = len([p for p in projects if p.get('status') in {'進行中', 'レビュー中'}])
        companies_summary.append({
            'name': company['name'],
            'project_count': len(projects),
            'completed_count': completed,
            'in_progress_count': in_progress
        })

    return {
        'summary': summary,
        'invoices': invoices,
        'payouts': payouts,
        'invoice_by_status': invoice_by_status,
        'payout_by_status': payout_by_status,
        'companies_summary': companies_summary
    }


def format_currency(value: int | float | None) -> str:
    if value is None:
        return '¥0'
    return f"¥{int(value):,}"


def build_finance_report_pdf(report_data, generated_by: str | None = None) -> BytesIO:
    ensure_reportlab_font()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 20 * mm
    margin_y = 20 * mm
    line_height = 7 * mm

    def draw_heading(text, size=16, offset=0):
        nonlocal current_y
        c.setFont(REPORT_PDF_FONT_NAME, size)
        c.drawString(margin_x, current_y + offset, text)

    def draw_body(text, size=11):
        nonlocal current_y
        if current_y < margin_y:
            c.showPage()
            current_y = height - margin_y
            c.setFont(REPORT_PDF_FONT_NAME, 11)
        c.setFont(REPORT_PDF_FONT_NAME, size)
        c.drawString(margin_x, current_y, text)
        current_y -= line_height

    current_y = height - margin_y

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    draw_heading("案件管理システム 収支レポート", size=18)
    current_y -= line_height
    draw_body(f"作成日時: {timestamp}")
    if generated_by:
        draw_body(f"作成者: {generated_by}")
    current_y -= line_height / 2

    summary = report_data['summary']
    draw_heading("サマリ", size=14)
    current_y -= line_height
    draw_body(f"総売上: {format_currency(summary['total_revenue'])}")
    draw_body(f"総コスト: {format_currency(summary['total_cost'])}")
    draw_body(f"粗利: {format_currency(summary['profit'])}")
    draw_body(f"粗利率: {summary['profit_rate']}%")

    current_y -= line_height / 2
    draw_heading("請求ステータス別集計", size=14)
    current_y -= line_height
    invoice_stats = report_data['invoice_by_status']
    if invoice_stats:
        for label, stats in invoice_stats.items():
            draw_body(f"{label}: 件数 {stats['count']}件 / 金額 {format_currency(stats['total'])}")
    else:
        draw_body("データがありません。")

    current_y -= line_height / 2
    draw_heading("支払ステータス別集計", size=14)
    current_y -= line_height
    payout_stats = report_data['payout_by_status']
    if payout_stats:
        for label, stats in payout_stats.items():
            draw_body(f"{label}: 件数 {stats['count']}件 / 金額 {format_currency(stats['total'])}")
    else:
        draw_body("データがありません。")

    current_y -= line_height / 2
    draw_heading("会社別案件サマリ", size=14)
    current_y -= line_height
    companies = report_data['companies_summary']
    if companies:
        for company in companies:
            draw_body(
                f"{company['name']}: 案件数 {company['project_count']}件 / 進行中 {company['in_progress_count']}件 / 完了 {company['completed_count']}件"
            )
    else:
        draw_body("データがありません。")

    current_y -= line_height / 2
    draw_heading("最新請求一覧 (最大10件)", size=14)
    current_y -= line_height
    invoices = report_data['invoices'][:10]
    if invoices:
        for invoice in invoices:
            draw_body(
                f"{invoice['project_name']} | {format_currency(invoice['amount'])} | 発行日: {invoice['issue_date'] or '---'} | 状態: {invoice['status_label']}"
            )
    else:
        draw_body("データがありません。")

    current_y -= line_height / 2
    draw_heading("最新支払一覧 (最大10件)", size=14)
    current_y -= line_height
    payouts = report_data['payouts'][:10]
    if payouts:
        for payout in payouts:
            draw_body(
                f"{payout['editor']} / {payout['project_name']} | {format_currency(payout['amount'])} | 状態: {payout['status_label']}"
            )
    else:
        draw_body("データがありません。")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def normalize_amount(value, field_label: str) -> int:
    if value is None:
        raise ValueError(f'{field_label}は必須です')
    if isinstance(value, (int, float)):
        amount = int(value)
    else:
        cleaned = str(value).replace(',', '').strip()
        if not cleaned:
            raise ValueError(f'{field_label}は必須です')
        try:
            amount = int(float(cleaned))
        except (TypeError, ValueError):
            raise ValueError(f'{field_label}は数値で入力してください')
    if amount < 0:
        raise ValueError(f'{field_label}は0以上の数値で入力してください')
    return amount


def normalize_date_string(value: str | None, field_label: str) -> str:
    if not value:
        return ''
    value = value.strip()
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f'{field_label}はYYYY-MM-DD形式で入力してください')
    return value


def validate_invoice_payload(data: dict) -> tuple[dict, list[str]]:
    errors = []
    project_name = (data.get('project_name') or '').strip()
    status = (data.get('status') or 'draft').strip()
    issue_date_raw = data.get('issue_date')

    if not project_name:
        errors.append('案件名は必須です')

    if status not in FINANCE_INVOICE_STATUS_LABELS:
        errors.append('請求ステータスが不正です')

    amount = None
    try:
        amount = normalize_amount(data.get('amount'), '請求金額')
    except ValueError as exc:
        errors.append(str(exc))

    issue_date = ''
    if issue_date_raw:
        try:
            issue_date = normalize_date_string(issue_date_raw, '発行日')
        except ValueError as exc:
            errors.append(str(exc))

    payload = {
        'project_name': project_name,
        'amount': amount,
        'status': status,
        'issue_date': issue_date
    }
    return payload, errors


def validate_payout_payload(data: dict) -> tuple[dict, list[str]]:
    errors = []
    editor = (data.get('editor') or '').strip()
    project_name = (data.get('project_name') or '').strip()
    status = (data.get('status') or 'pending').strip()

    if not editor:
        errors.append('編集者名は必須です')
    if not project_name:
        errors.append('案件名は必須です')

    if status not in FINANCE_PAYOUT_STATUS_LABELS:
        errors.append('支払ステータスが不正です')

    amount = None
    try:
        amount = normalize_amount(data.get('amount'), '支払金額')
    except ValueError as exc:
        errors.append(str(exc))

    payload = {
        'editor': editor,
        'project_name': project_name,
        'amount': amount,
        'status': status
    }
    return payload, errors


def get_invoice_by_id(invoice_id: int) -> dict | None:
    return next((invoice for invoice in FINANCE_INVOICES if invoice['id'] == invoice_id), None)


def get_payout_by_id(payout_id: int) -> dict | None:
    return next((payout for payout in FINANCE_PAYOUTS if payout['id'] == payout_id), None)


@app.route('/finance')
def finance():
    """請求・収支"""
    summary = calculate_finance_summary()
    finance_data = {
        **summary,
        'invoices': [serialize_invoice(invoice) for invoice in FINANCE_INVOICES],
        'payouts': [serialize_payout(payout) for payout in FINANCE_PAYOUTS]
    }
    return render_template(
        'finance.html',
        finance_data=finance_data,
        invoice_status_options=FINANCE_INVOICE_STATUS_OPTIONS,
        payout_status_options=FINANCE_PAYOUT_STATUS_OPTIONS,
        invoice_status_labels=FINANCE_INVOICE_STATUS_LABELS,
        payout_status_labels=FINANCE_PAYOUT_STATUS_LABELS
    )


@app.route('/api/finance/invoices', methods=['POST'])
@login_required
@role_required('admin')
def api_create_invoice():
    data = request.get_json(silent=True) or {}
    payload, errors = validate_invoice_payload(data)
    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    invoice = {
        'id': get_next_invoice_id(),
        **payload
    }
    FINANCE_INVOICES.append(invoice)
    summary = calculate_finance_summary()
    return jsonify({
        'status': 'success',
        'message': '請求を追加しました',
        'data': {
            'invoice': serialize_invoice(invoice),
            'summary': summary
        }
    })


@app.route('/api/finance/invoices/<int:invoice_id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_update_invoice(invoice_id):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        return jsonify({'status': 'error', 'message': '請求が見つかりません'}), 404

    data = request.get_json(silent=True) or {}
    payload, errors = validate_invoice_payload(data)
    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    invoice.update(payload)
    summary = calculate_finance_summary()
    return jsonify({
        'status': 'success',
        'message': '請求を更新しました',
        'data': {
            'invoice': serialize_invoice(invoice),
            'summary': summary
        }
    })


@app.route('/api/finance/payouts', methods=['POST'])
@login_required
@role_required('admin')
def api_create_payout():
    data = request.get_json(silent=True) or {}
    payload, errors = validate_payout_payload(data)
    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    payout = {
        'id': get_next_payout_id(),
        **payload
    }
    FINANCE_PAYOUTS.append(payout)
    summary = calculate_finance_summary()
    return jsonify({
        'status': 'success',
        'message': '支払を追加しました',
        'data': {
            'payout': serialize_payout(payout),
            'summary': summary
        }
    })


@app.route('/api/finance/payouts/<int:payout_id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_update_payout(payout_id):
    payout = get_payout_by_id(payout_id)
    if not payout:
        return jsonify({'status': 'error', 'message': '支払が見つかりません'}), 404

    data = request.get_json(silent=True) or {}
    payload, errors = validate_payout_payload(data)
    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    payout.update(payload)
    summary = calculate_finance_summary()
    return jsonify({
        'status': 'success',
        'message': '支払を更新しました',
        'data': {
            'payout': serialize_payout(payout),
            'summary': summary
        }
    })


@app.route('/reports')
def reports():
    """レポート"""
    return render_template('reports.html')


@app.route('/reports/download/finance')
@login_required
@role_required('admin')
def download_finance_report():
    if not REPORTLAB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': 'PDF生成ライブラリが利用できません。requirements.txt から reportlab をインストールしてください。'
        }), 503

    report_data = gather_finance_report_data()
    current_user = g.current_user
    generated_by = current_user['name'] if current_user and current_user.get('name') else None
    pdf_buffer = build_finance_report_pdf(report_data, generated_by=generated_by)
    filename = f"finance_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


# ===== 初期化フック =====
initialize_all_project_tasks()

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


@app.route('/client')
@login_required
@role_required('admin', 'editor', 'client')
def client_dashboard():
    """クライアント向けポータル"""
    context = build_client_portal_context(g.current_user)
    return render_template('client/index.html', **context)


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
    all_tasks = get_all_tasks()
    today_tasks = [
        t for t in all_tasks
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
        task_type_labels=TASK_TYPE_LABELS,
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


@app.route('/editor/input-videos')
@login_required
@role_required('admin', 'editor')
def editor_input_videos():
    """編集インプット動画一覧"""
    current_user = g.current_user
    include_watchers = current_user.get('role') == 'admin'
    videos = get_training_videos_for_portal(current_user, include_watchers=include_watchers)

    summary = {
        'total_videos': len(videos),
        'completed_count': len([v for v in videos if v['user_progress'] >= 100 or v['user_status'] == '視聴済']),
        'in_progress_count': len([v for v in videos if 0 < v['user_progress'] < 100 and v['user_status'] != '視聴済']),
        'not_started_count': len([v for v in videos if v['user_progress'] == 0 and v['user_status'] == '未視聴'])
    }
    overall_completion = 0
    if videos:
        overall_completion = int(round(sum(v['avg_progress'] for v in videos) / len(videos)))

    return render_template(
        'editor/training_videos.html',
        videos=videos,
        include_watchers=include_watchers,
        status_options=TRAINING_STATUS_OPTIONS,
        summary=summary,
        overall_completion=overall_completion
    )


@app.route('/editor/gantt')
@login_required
@role_required('admin', 'editor')
def editor_gantt():
    user_tasks = filter_tasks_for_user(get_all_tasks(), g.current_user)
    serialized_tasks = [serialize_gantt_task(task) for task in filter_tasks_by_params(user_tasks, {})]
    filters = collect_task_filters(user_tasks)
    return render_template(
        'gantt.html',
        base_template='editor_layout.html',
        initial_tasks=serialized_tasks,
        filter_options=filters,
        dependency_types=sorted(TASK_DEPENDENCY_TYPES),
        current_view='plan'
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
        next_url = normalize_next_url(request.form.get('next'))

        user = get_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            error = 'メールアドレスまたはパスワードが正しくありません。'
        elif not user.get('active', True):
            error = 'このユーザーは無効化されています。管理者に連絡してください。'
        else:
            session['user_id'] = user['id']
            default_endpoint = get_default_home_endpoint(user.get('role'))
            role = (user.get('role') or '').lower()
            if role == 'client':
                return redirect(url_for(default_endpoint))
            if role != 'admin':
                return redirect(url_for(default_endpoint))
            return redirect(next_url or url_for(default_endpoint))

    next_url = normalize_next_url(request.args.get('next'))
    return render_template('auth/login.html', error=error, next_url=next_url or '')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.pop('user_id', None)
    next_url = normalize_next_url(request.form.get('next'), default_endpoint='login')
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
                password_hash=hash_password(password),
                active=active
            )
            workspace_message = ''
            if new_user['role'] == 'editor':
                create_editor_workspace_for_user(new_user)
                workspace_message = ' 編集者用共有ページも自動生成されました。'
            elif new_user['role'] == 'client':
                ensure_client_portal_profile(new_user)
                workspace_message = ' クライアント専用ポータルが割り当てられました。'
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

def get_training_videos_for_portal(user, include_watchers=False):
    videos = fetch_all(
        """
        select
            tv.id,
            tv.title,
            tv.description,
            tv.url,
            tv.duration_minutes,
            tv.created_at,
            tv.created_by,
            creator.name as created_by_name,
            coalesce(stats.total_viewers, 0) as total_viewers,
            coalesce(stats.completed_viewers, 0) as completed_viewers,
            coalesce(stats.avg_progress, 0) as avg_progress
        from app.training_videos tv
        left join app.users creator on creator.id = tv.created_by
        left join (
            select
                video_id,
                count(*) filter (where status <> '未視聴') as total_viewers,
                count(*) filter (where status in ('視聴済', '完了')) as completed_viewers,
                avg(progress_percent) as avg_progress
            from app.training_video_progress
            group by video_id
        ) stats on stats.video_id = tv.id
        order by tv.created_at desc
        """
    )

    user_progress_map = {}
    if user:
        progress_rows = fetch_all(
            """
            select video_id, status, progress_percent, last_viewed_at, notes
            from app.training_video_progress
            where user_id = :user_id
            """,
            user_id=user['id']
        )
        for row in progress_rows:
            user_progress_map[row['video_id']] = row

    watchers_map = {}
    if include_watchers:
        watcher_rows = fetch_all(
            """
            select
                p.video_id,
                u.name,
                u.email,
                p.status,
                p.progress_percent,
                p.last_viewed_at
            from app.training_video_progress p
            join app.users u on u.id = p.user_id
            order by p.video_id, u.name
            """
        )
        for row in watcher_rows:
            watchers_map.setdefault(row['video_id'], []).append({
                'name': row['name'],
                'email': row['email'],
                'status': row['status'],
                'progress_percent': row['progress_percent'],
                'last_viewed_at': serialize_datetime(row['last_viewed_at'])
            })

    results = []
    for video in videos:
        progress = user_progress_map.get(video['id'])
        video_context = {
            'id': video['id'],
            'title': video['title'],
            'description': video.get('description') or '',
            'url': video['url'],
            'duration_minutes': video.get('duration_minutes'),
            'created_at': serialize_datetime(video.get('created_at')),
            'created_by_name': video.get('created_by_name') or '管理者',
            'total_viewers': video.get('total_viewers', 0),
            'completed_viewers': video.get('completed_viewers', 0),
            'avg_progress': normalize_percent(video.get('avg_progress')),
            'user_status': progress['status'] if progress else '未視聴',
            'user_progress': progress['progress_percent'] if progress else 0,
            'user_last_viewed': serialize_datetime(progress.get('last_viewed_at')) if progress and progress.get('last_viewed_at') else None,
            'user_notes': progress.get('notes') if progress else ''
        }
        if include_watchers:
            video_context['watchers'] = watchers_map.get(video['id'], [])
        results.append(video_context)

    return results


def get_training_video_context(video_id: int, user, include_watchers=False):
    videos = get_training_videos_for_portal(user, include_watchers=include_watchers)
    return next((video for video in videos if video['id'] == video_id), None)


def upsert_training_progress(video_id: int, user_id: int, status: str, progress_percent: int, notes: str = ''):
    status = status if status in TRAINING_STATUS_OPTIONS else '視聴中'
    progress_percent = max(0, min(100, progress_percent))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into app.training_video_progress (video_id, user_id, status, progress_percent, last_viewed_at, notes)
                values (:video_id, :user_id, :status, :progress_percent, :last_viewed_at, :notes)
                on conflict (video_id, user_id) do update set
                    status = excluded.status,
                    progress_percent = excluded.progress_percent,
                    last_viewed_at = excluded.last_viewed_at,
                    notes = excluded.notes
                """
            ),
            video_id=video_id,
            user_id=user_id,
            status=status,
            progress_percent=progress_percent,
            last_viewed_at=datetime.now(),
            notes=notes
        )

@app.route('/api/editor/training-videos/<int:video_id>/progress', methods=['POST'])
@login_required
@role_required('admin', 'editor')
def api_update_training_video_progress(video_id):
    """編集インプット動画の進捗更新"""
    video = fetch_one("select id from app.training_videos where id = :video_id", video_id=video_id)
    if not video:
        return jsonify({'status': 'error', 'message': '動画が見つかりません'}), 404

    data = request.get_json() or {}
    status = (data.get('status') or '視聴中').strip()
    notes = data.get('notes', '').strip()

    try:
        progress_value = int(data.get('progress_percent', data.get('progress', 0)))
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': '進捗は0〜100の範囲で入力してください'}), 400

    upsert_training_progress(
        video_id=video_id,
        user_id=g.current_user['id'],
        status=status,
        progress_percent=progress_value,
        notes=notes
    )

    video_context = get_training_video_context(
        video_id,
        g.current_user,
        include_watchers=g.current_user.get('role') == 'admin'
    )
    return jsonify({
        'status': 'success',
        'message': '進捗を更新しました',
        'data': video_context
    })


@app.route('/api/admin/training-videos', methods=['POST'])
@login_required
@role_required('admin')
def api_admin_create_training_video():
    """管理者: 編集インプット動画の登録"""
    form = request.form
    files = request.files

    title = (form.get('title') or '').strip()
    url_value = (form.get('url') or '').strip()
    description = (form.get('description') or '').strip()
    duration_value = form.get('duration_minutes', form.get('duration'))
    uploaded_file = files.get('video_file') if files else None

    errors = []
    if not title:
        errors.append('タイトルは必須です')

    video_url = None
    if uploaded_file and uploaded_file.filename:
        filename = uploaded_file.filename
        if not allowed_training_video_filename(filename):
            errors.append('対応していない動画形式です (mp4, mov, avi, mkv, wmv, m4v)')
        else:
            extension = filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid4().hex}.{extension}"
            safe_name = secure_filename(unique_name)
            save_path = os.path.join(TRAINING_VIDEO_UPLOAD_FOLDER, safe_name)
            uploaded_file.save(save_path)
            video_url = url_for('serve_training_video', filename=safe_name)
    elif url_value:
        video_url = url_value
    else:
        errors.append('動画URLまたは動画ファイルのいずれかを指定してください')

    duration_minutes = None
    if duration_value not in (None, ''):
        try:
            duration_minutes = int(duration_value)
            if duration_minutes < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append('想定視聴時間は0以上の数値で入力してください')

    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                insert into app.training_videos (title, description, url, duration_minutes, created_by)
                values (:title, :description, :url, :duration_minutes, :created_by)
                returning id
                """
            ),
            {
                'title': title,
                'description': description,
                'url': video_url,
                'duration_minutes': duration_minutes,
                'created_by': g.current_user['id']
            }
        )
        new_id = result.scalar()

    video_context = get_training_video_context(new_id, g.current_user, include_watchers=True)
    return jsonify({
        'status': 'success',
        'message': '動画を登録しました',
        'data': video_context
    })


def get_training_video_file_path(video_url: str) -> str | None:
    """保存済み動画URLからローカルファイルパスを取得"""
    if not video_url:
        return None
    try:
        base_prefix = url_for('serve_training_video', filename='')
    except RuntimeError:
        base_prefix = '/uploads/training_videos/'
    if not video_url.startswith(base_prefix):
        return None
    filename = video_url[len(base_prefix):].lstrip('/')
    if not filename:
        return None
    return os.path.join(TRAINING_VIDEO_UPLOAD_FOLDER, filename)


def remove_training_video_file(video_url: str):
    """ローカルに保存している動画ファイルを削除"""
    file_path = get_training_video_file_path(video_url)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            app.logger.warning("Failed to remove training video file: %s", file_path)


def save_training_video_upload(uploaded_file):
    """アップロードされた動画ファイルを保存しURLを返す"""
    if not uploaded_file or not uploaded_file.filename:
        return None, '動画ファイルが選択されていません'

    filename = uploaded_file.filename
    if not allowed_training_video_filename(filename):
        return None, '対応していない動画形式です (mp4, mov, avi, mkv, wmv, m4v)'

    extension = filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid4().hex}.{extension}"
    safe_name = secure_filename(unique_name)
    save_path = os.path.join(TRAINING_VIDEO_UPLOAD_FOLDER, safe_name)
    uploaded_file.save(save_path)
    return url_for('serve_training_video', filename=safe_name), None


@app.route('/api/admin/training-videos/<int:video_id>', methods=['PUT'])
@login_required
@role_required('admin')
def api_admin_update_training_video(video_id):
    """管理者: 編集インプット動画の更新"""
    existing = fetch_one(
        "select id, title, description, url, duration_minutes from app.training_videos where id = :video_id",
        video_id=video_id
    )
    if not existing:
        return jsonify({'status': 'error', 'message': '動画が見つかりません'}), 404

    form = request.form
    files = request.files

    title = (form.get('title') or '').strip()
    description = (form.get('description') or '').strip()
    url_value = (form.get('url') or '').strip()
    duration_value = form.get('duration_minutes', form.get('duration'))
    uploaded_file = files.get('video_file') if files else None

    errors = []
    if not title:
        errors.append('タイトルは必須です')

    video_url = existing['url']
    old_url_to_remove = None

    if uploaded_file and uploaded_file.filename:
        saved_url, upload_error = save_training_video_upload(uploaded_file)
        if upload_error:
            errors.append(upload_error)
        else:
            if video_url != saved_url and get_training_video_file_path(video_url):
                old_url_to_remove = video_url
            video_url = saved_url
    elif url_value:
        if url_value != video_url and get_training_video_file_path(video_url):
            old_url_to_remove = video_url
        video_url = url_value

    duration_minutes = existing.get('duration_minutes')
    if duration_value not in (None, ''):
        try:
            duration_minutes = int(duration_value)
            if duration_minutes < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append('想定視聴時間は0以上の数値で入力してください')

    if not video_url:
        errors.append('動画URLまたは動画ファイルのいずれかを指定してください')

    if errors:
        return jsonify({'status': 'error', 'message': ' / '.join(errors)}), 400

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                update app.training_videos
                set title = :title,
                    description = :description,
                    url = :url,
                    duration_minutes = :duration_minutes
                where id = :video_id
                """
            ),
            {
                'video_id': video_id,
                'title': title,
                'description': description,
                'url': video_url,
                'duration_minutes': duration_minutes
            }
        )

    if old_url_to_remove:
        remove_training_video_file(old_url_to_remove)

    video_context = get_training_video_context(video_id, g.current_user, include_watchers=True)
    return jsonify({
        'status': 'success',
        'message': '動画を更新しました',
        'data': video_context
    })


@app.route('/api/admin/training-videos/<int:video_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def api_admin_delete_training_video(video_id):
    """管理者: 編集インプット動画の削除"""
    existing = fetch_one(
        "select id, url from app.training_videos where id = :video_id",
        video_id=video_id
    )
    if not existing:
        return jsonify({'status': 'error', 'message': '動画が見つかりません'}), 404

    with engine.begin() as conn:
        conn.execute(
            text("delete from app.training_videos where id = :video_id"),
            {'video_id': video_id}
        )

    remove_training_video_file(existing['url'])

    return jsonify({
        'status': 'success',
        'message': '動画を削除しました'
    })

@app.route('/admin/training-videos')
@login_required
@role_required('admin')
def admin_training_videos():
    """管理者向け編集インプット動画管理"""
    videos = get_training_videos_for_portal(g.current_user, include_watchers=True)
    summary = {
        'total_videos': len(videos),
        'completed_count': len([v for v in videos if v['avg_progress'] >= 99]),
        'in_progress_count': len([v for v in videos if 0 < v['avg_progress'] < 99]),
        'not_started_count': len([v for v in videos if v['avg_progress'] == 0])
    }
    overall_completion = int(round(sum(v['avg_progress'] for v in videos) / len(videos))) if videos else 0
    return render_template(
        'admin/training_videos.html',
        videos=videos,
        status_options=TRAINING_STATUS_OPTIONS,
        summary=summary,
        overall_completion=overall_completion
    )


@app.route('/admin/gantt')
@login_required
@role_required('admin')
def admin_gantt():
    user_tasks = filter_tasks_for_user(get_all_tasks(), g.current_user)
    filter_options = collect_task_filters(user_tasks)

    params = {
        'project_id': (request.args.get('project_id') or '').strip(),
        'assignee': (request.args.get('assignee') or '').strip(),
        'status': (request.args.get('status') or '').strip(),
        'keyword': (request.args.get('keyword') or '').strip(),
        'start_date': (request.args.get('start_date') or '').strip(),
        'end_date': (request.args.get('end_date') or '').strip()
    }

    filtered_task_entries = filter_tasks_by_params(user_tasks, params)
    serialized_tasks = [serialize_gantt_task(task) for task in filtered_task_entries]

    project_summary_all = summarize_projects_for_gantt()
    filtered_summary = filter_project_summary_entries(project_summary_all, params, filtered_task_entries)

    return render_template(
        'gantt.html',
        base_template='layout.html',
        initial_tasks=serialized_tasks,
        project_summary=filtered_summary,
        filter_options=filter_options,
        selected_filters=params,
        project_choices=filter_options.get('projects', []),
        dependency_types=sorted(TASK_DEPENDENCY_TYPES),
        current_view='plan'
    )


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5001)


@app.route('/uploads/training_videos/<path:filename>')
@login_required
@role_required('admin', 'editor')
def serve_training_video(filename):
    return send_from_directory(TRAINING_VIDEO_UPLOAD_FOLDER, filename)

