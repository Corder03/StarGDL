from flask import Flask, render_template, request, jsonify, send_file, Response, redirect, url_for, flash
import os
import io
import base64
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import SquareModuleDrawer
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
import json
import pytz
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================
# CONFIGURAÇÃO DO FUSO HORÁRIO
# ============================================
BRASIL_TZ = pytz.timezone('America/Sao_Paulo')

def agora_brasil():
    """Retorna datetime atual no fuso horário de São Paulo"""
    return datetime.now(BRASIL_TZ)

# ============================================
# AUTENTICAÇÃO
# ============================================
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

login_manager = LoginManager()
login_manager.login_view = None

@login_manager.user_loader
def load_user(user_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                if user:
                    return User(id=user[0], username=user[1], role=user[2])
    except:
        pass
    return None

# ============================================
# CONFIGURAÇÃO OTIMIZADA
# ============================================
DATABASE_URL = os.environ.get('DATABASE_URL', 
    "postgresql://neondb_owner:npg_u3KBSnf7XWGA@ep-cold-wind-api54jnp-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

connection_pool = None

def get_connection():
    """Retorna conexão do pool ou cria nova"""
    global connection_pool
    try:
        if connection_pool is None or connection_pool.closed:
            connection_pool = psycopg2.connect(
                DATABASE_URL, 
                keepalives=1, 
                keepalives_idle=30, 
                keepalives_interval=10,
                keepalives_count=5,
                options='-c timezone=America/Sao_Paulo'
            )
        with connection_pool.cursor() as cur:
            cur.execute("SELECT 1")
        return connection_pool
    except:
        connection_pool = psycopg2.connect(
            DATABASE_URL,
            options='-c timezone=America/Sao_Paulo'
        )
        return connection_pool

@contextmanager
def get_db():
    """Contexto de banco de dados otimizado"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'America/Sao_Paulo';")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

# Configuração de diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
FONTS_DIR = os.path.join(BASE_DIR, 'fonts')

print(f"📁 BASE_DIR: {BASE_DIR}")
print(f"📁 FONTS_DIR: {FONTS_DIR}")
print(f"📁 Fontes disponíveis: {os.listdir(FONTS_DIR) if os.path.exists(FONTS_DIR) else 'PASTA NÃO ENCONTRADA!'}")
print(f"🕐 Fuso horário configurado: America/Sao_Paulo")

# ============================================
# INICIALIZAÇÃO DO BANCO
# ============================================
def init_db():
    """Cria tabelas se não existirem"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'America/Sao_Paulo';")
                
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS modelos (
                        id TEXT PRIMARY KEY,
                        marca TEXT NOT NULL,
                        modelo TEXT NOT NULL,
                        processador TEXT DEFAULT '',
                        ram TEXT DEFAULT '',
                        armazenamento TEXT DEFAULT '',
                        observacao TEXT DEFAULT '',
                        data_criacao TEXT DEFAULT '',
                        saldo_atual INTEGER DEFAULT 0
                    )
                ''')
                
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'modelos' AND column_name = 'observacao'")
                if cur.fetchone() is None:
                    cur.execute("ALTER TABLE modelos ADD COLUMN observacao TEXT DEFAULT ''")
                
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS movimentacoes (
                        id SERIAL PRIMARY KEY,
                        modelo_id TEXT NOT NULL,
                        quantidade INTEGER NOT NULL,
                        tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
                        data TIMESTAMPTZ DEFAULT NOW() NOT NULL
                    )
                ''')

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS maquinas_modelos (
                        id TEXT PRIMARY KEY,
                        marca TEXT NOT NULL,
                        modelo TEXT NOT NULL,
                        processador TEXT DEFAULT '',
                        ram TEXT DEFAULT '',
                        armazenamento TEXT DEFAULT '',
                        localizacao TEXT DEFAULT '',
                        data_criacao TEXT DEFAULT '',
                        saldo_atual INTEGER DEFAULT 0
                    )
                ''')

                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'maquinas_modelos' AND column_name = 'localizacao'")
                if cur.fetchone() is None:
                    cur.execute("ALTER TABLE maquinas_modelos ADD COLUMN localizacao TEXT DEFAULT ''")

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS maquinas_movimentacoes (
                        id SERIAL PRIMARY KEY,
                        modelo_id TEXT NOT NULL,
                        quantidade INTEGER NOT NULL,
                        tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
                        data TIMESTAMPTZ DEFAULT NOW() NOT NULL
                    )
                ''')

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS maquinas_qr_codes (
                        modelo_id TEXT PRIMARY KEY,
                        imagem_base64 TEXT NOT NULL,
                        data_criacao TIMESTAMPTZ DEFAULT NOW(),
                        FOREIGN KEY (modelo_id) REFERENCES maquinas_modelos(id) ON DELETE CASCADE
                    )
                ''')

                cur.execute('CREATE INDEX IF NOT EXISTS idx_maquinas_mov_modelo ON maquinas_movimentacoes(modelo_id)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_maquinas_mov_tipo ON maquinas_movimentacoes(tipo)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_maquinas_mov_data ON maquinas_movimentacoes(data)')

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS qr_codes (
                        modelo_id TEXT PRIMARY KEY,
                        imagem_base64 TEXT NOT NULL,
                        data_criacao TIMESTAMPTZ DEFAULT NOW(),
                        FOREIGN KEY (modelo_id) REFERENCES modelos(id) ON DELETE CASCADE
                    )
                ''')
                
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                
                # ========== TABELAS PARA MONITORES ==========
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS monitores_modelos (
                        id TEXT PRIMARY KEY,
                        marca TEXT NOT NULL,
                        modelo TEXT NOT NULL,
                        tamanho TEXT DEFAULT '',
                        resolucao TEXT DEFAULT '',
                        taxa_refresh TEXT DEFAULT '',
                        tipo_painel TEXT DEFAULT '',
                        localizacao TEXT DEFAULT '',
                        data_criacao TEXT DEFAULT '',
                        saldo_atual INTEGER DEFAULT 0
                    )
                ''')

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS monitores_movimentacoes (
                        id SERIAL PRIMARY KEY,
                        modelo_id TEXT NOT NULL,
                        quantidade INTEGER NOT NULL,
                        tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
                        data TIMESTAMPTZ DEFAULT NOW() NOT NULL
                    )
                ''')

                cur.execute('''
                    CREATE TABLE IF NOT EXISTS monitores_qr_codes (
                        modelo_id TEXT PRIMARY KEY,
                        imagem_base64 TEXT NOT NULL,
                        data_criacao TIMESTAMPTZ DEFAULT NOW(),
                        FOREIGN KEY (modelo_id) REFERENCES monitores_modelos(id) ON DELETE CASCADE
                    )
                ''')

                cur.execute('CREATE INDEX IF NOT EXISTS idx_monitores_mov_modelo ON monitores_movimentacoes(modelo_id)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_monitores_mov_tipo ON monitores_movimentacoes(tipo)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_monitores_mov_data ON monitores_movimentacoes(data)')
                
                cur.execute('CREATE INDEX IF NOT EXISTS idx_mov_modelo ON movimentacoes(modelo_id)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_mov_tipo ON movimentacoes(tipo)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_mov_data ON movimentacoes(data)')
                
                cur.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
                if cur.fetchone()[0] == 0:
                    admin_password = generate_password_hash('admin8216@')
                    cur.execute('''
                        INSERT INTO users (username, password_hash, role)
                        VALUES (%s, %s, %s)
                    ''', ('admin', admin_password, 'admin'))
        
        print("✅ Banco de dados inicializado com sucesso!")
        print("🕐 Timezone configurado: America/Sao_Paulo")
        print("👤 Usuário admin criado (senha: admin8216@)")
        print("🖥️ Tabelas de monitores criadas!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco: {e}")
        raise

# ============================================
# FUNÇÕES AUXILIARES
# ============================================
def calcular_saldo(modelo_id):
    """Calcula saldo - Query otimizada"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade ELSE -quantidade END), 0) as saldo
                FROM movimentacoes WHERE modelo_id = %s
            ''', (modelo_id,))
            return cur.fetchone()[0]

def get_modelo_com_saldo(modelo_id):
    """Busca modelo + saldo em UMA ÚNICA query"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                       m.observacao, m.data_criacao, m.saldo_atual,
                       COALESCE(
                            (SELECT SUM(CASE WHEN tipo = 'entrada' THEN quantidade ELSE -quantidade END) 
                             FROM movimentacoes WHERE modelo_id = %s), 0) as saldo
                FROM modelos m WHERE m.id = %s
            ''', (modelo_id, modelo_id))
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0], 'marca': row[1], 'modelo': row[2],
                    'processador': row[3], 'ram': row[4], 'armazenamento': row[5],
                    'observacao': row[6], 'data_criacao': row[7],
                    'saldo_atual': row[8], 'saldo': row[9]
                }
            return None

def get_maquina_com_saldo(modelo_id):
    """Busca máquina + saldo em UMA ÚNICA query (tabelas separadas)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                       m.localizacao, m.data_criacao, m.saldo_atual,
                       COALESCE(
                            (SELECT SUM(CASE WHEN tipo = 'entrada' THEN quantidade ELSE -quantidade END) 
                             FROM maquinas_movimentacoes WHERE modelo_id = %s), 0) as saldo
                FROM maquinas_modelos m WHERE m.id = %s
            ''', (modelo_id, modelo_id))
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0], 'marca': row[1], 'modelo': row[2],
                    'processador': row[3], 'ram': row[4], 'armazenamento': row[5],
                    'localizacao': row[6], 'data_criacao': row[7],
                    'saldo_atual': row[8], 'saldo': row[9]
                }
            return None

def get_monitor_com_saldo(modelo_id):
    """Busca monitor + saldo"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT m.id, m.marca, m.modelo, m.tamanho, m.resolucao, m.taxa_refresh, m.tipo_painel,
                       m.localizacao, m.data_criacao, m.saldo_atual,
                       COALESCE(
                            (SELECT SUM(CASE WHEN tipo = 'entrada' THEN quantidade ELSE -quantidade END) 
                             FROM monitores_movimentacoes WHERE modelo_id = %s), 0) as saldo
                FROM monitores_modelos m WHERE m.id = %s
            ''', (modelo_id, modelo_id))
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0], 'marca': row[1], 'modelo': row[2],
                    'tamanho': row[3], 'resolucao': row[4], 'taxa_refresh': row[5],
                    'tipo_painel': row[6], 'localizacao': row[7], 'data_criacao': row[8],
                    'saldo_atual': row[9], 'saldo': row[10]
                }
            return None

def formatar_data_brasil(data):
    """Formata data para o padrão brasileiro"""
    if isinstance(data, datetime):
        if data.tzinfo is None:
            data = pytz.UTC.localize(data)
        data_brasil = data.astimezone(BRASIL_TZ)
        return data_brasil.strftime('%d/%m/%Y %H:%M:%S')
    return str(data)

def carregar_fontes():
    """Carrega fontes TrueType da pasta 'fonts' do projeto"""
    fontes = {}
    
    if not os.path.exists(FONTS_DIR):
        print(f"❌ Pasta de fontes não encontrada: {FONTS_DIR}")
        return carregar_fontes_fallback()
    
    fonte_bold = os.path.join(FONTS_DIR, 'DejaVuSans-Bold.ttf')
    fonte_regular = os.path.join(FONTS_DIR, 'DejaVuSans.ttf')
    
    tem_bold = os.path.exists(fonte_bold)
    tem_regular = os.path.exists(fonte_regular)
    
    print(f"🔍 Procurando fontes:")
    print(f"   Bold: {fonte_bold} {'✅' if tem_bold else '❌'}")
    print(f"   Regular: {fonte_regular} {'✅' if tem_regular else '❌'}")
    
    if not tem_bold and not tem_regular:
        print("❌ Nenhuma fonte encontrada na pasta 'fonts'!")
        return carregar_fontes_fallback()
    
    tamanhos = {
        'nome': 28,
        'spec_label': 24,
        'spec_valor': 22,
        'id': 18,
        'scan': 20,
    }
    
    print("🔤 Carregando fontes com tamanhos AUMENTADOS:")
    
    for nome, tamanho in tamanhos.items():
        carregada = False
        
        if tem_bold:
            try:
                fontes[nome] = ImageFont.truetype(fonte_bold, tamanho)
                carregada = True
                print(f"   ✅ {nome}: DejaVuSans-Bold {tamanho}px")
            except Exception as e:
                print(f"   ⚠️ Erro ao carregar Bold para {nome}: {e}")
        
        if not carregada and tem_regular:
            try:
                fontes[nome] = ImageFont.truetype(fonte_regular, tamanho)
                carregada = True
                print(f"   ⚠️ {nome}: DejaVuSans-Regular {tamanho}px (não é bold)")
            except Exception as e:
                print(f"   ⚠️ Erro ao carregar Regular para {nome}: {e}")
        
        if not carregada:
            print(f"   ❌ {nome}: usando fallback do sistema")
            return carregar_fontes_fallback()
    
    print("✅ Fontes carregadas com sucesso da pasta local!")
    return fontes

def carregar_fontes_fallback():
    """Fallback quando as fontes locais não estão disponíveis"""
    fontes = {}
    
    print("⚠️ Usando FALLBACK de fontes...")
    
    system_fonts_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText-Bold.ttf",
        "C:/Windows/Fonts/Arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
    ]
    
    system_fonts_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/SFNSText-Regular.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]
    
    tamanhos = {
        'nome': 40,
        'spec_label': 35,
        'spec_valor': 30,
        'id': 25,
        'scan': 28,
    }
    
    for nome, tamanho in tamanhos.items():
        carregada = False
        
        for font_path in system_fonts_bold:
            try:
                if os.path.exists(font_path):
                    fontes[nome] = ImageFont.truetype(font_path, tamanho)
                    carregada = True
                    print(f"   ✅ {nome}: {os.path.basename(font_path)} {tamanho}px (sistema)")
                    break
            except:
                continue
        
        if not carregada:
            for font_path in system_fonts_regular:
                try:
                    if os.path.exists(font_path):
                        fontes[nome] = ImageFont.truetype(font_path, tamanho)
                        carregada = True
                        print(f"   ⚠️ {nome}: {os.path.basename(font_path)} {tamanho}px (regular)")
                        break
                except:
                    continue
        
        if not carregada:
            print(f"   ❌ {nome}: usando load_default() - TEXTOS FICARÃO PEQUENOS!")
            fontes[nome] = ImageFont.load_default()
    
    return fontes

def wrap_text(text, font, max_width, draw):
    """Quebra texto em múltiplas linhas para caber numa largura máxima."""
    if not text:
        return ['']

    words = text.split()
    lines = []
    current_line = ''

    for word in words:
        candidate = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines

# ============================================
# APP FLASK - CRIAR ANTES DE TODAS AS ROTAS
# ============================================
app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config['SECRET_KEY'] = '4mc-estoque-2024'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Inicializar Login Manager
login_manager.init_app(app)

# Configurar timezone global no Jinja2
@app.context_processor
def inject_now():
    return {'now': agora_brasil()}

# Inicializar banco de dados
init_db()

# ============================================
# ROTAS DE AUTENTICAÇÃO
# ============================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, password_hash, role FROM users WHERE username = %s", (username,))
                user_data = cur.fetchone()
                
                if user_data and check_password_hash(user_data[2], password):
                    user = User(id=user_data[0], username=user_data[1], role=user_data[3])
                    login_user(user)
                    next_page = request.args.get('next')
                    return redirect(next_page) if next_page else redirect(url_for('index'))
        
        flash('Usuário ou senha inválidos')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ============================================
# ROTAS PÚBLICAS (VISUALIZAÇÃO)
# ============================================
@app.route('/')
def index():
    print("🔍 Rota index chamada!")
    return render_template('index.html', current_user=current_user)

@app.route('/gerar')
@login_required
def gerar():
    if current_user.role != 'admin':
        flash('Acesso negado: apenas administradores podem gerar QR codes')
        return redirect(url_for('index'))
    return render_template('gerar_qr.html')

@app.route('/maquinas')
def maquinas_page():
    return render_template('maquinas_index.html', current_user=current_user)

@app.route('/gerar_maquinas')
@login_required
def gerar_maquinas_page():
    if current_user.role != 'admin':
        flash('Acesso negado: apenas administradores podem gerar QR codes')
        return redirect(url_for('index'))
    return render_template('gerar_qr_maquinas.html')

@app.route('/monitores')
def monitores_page():
    return render_template('monitores_index.html', current_user=current_user)

@app.route('/gerar_monitores')
@login_required
def gerar_monitores_page():
    if current_user.role != 'admin':
        flash('Acesso negado: apenas administradores podem gerar QR codes')
        return redirect(url_for('index'))
    return render_template('gerar_qr_monitores.html')

@app.route('/scan/<modelo_id>')
def scan(modelo_id):
    """Página de scan para notebooks"""
    try:
        modelo = get_modelo_com_saldo(modelo_id)
        if modelo:
            return render_template('scan.html', modelo=modelo, duplicado=False, tipo_maquina=False, tipo_monitor=False)
        else:
            return render_template('scan.html', modelo=None, erro=f'Modelo {modelo_id} não encontrado', tipo_maquina=False, tipo_monitor=False)
    except Exception as e:
        return render_template('scan.html', modelo=None, erro=f'Erro: {str(e)}', tipo_maquina=False, tipo_monitor=False)

@app.route('/scan_maquinas/<modelo_id>')
def scan_maquinas(modelo_id):
    """Página de scan para máquinas"""
    try:
        maquina = get_maquina_com_saldo(modelo_id)
        if maquina:
            return render_template('scan.html', modelo=maquina, duplicado=False, tipo_maquina=True, tipo_monitor=False)
        return render_template('scan.html', modelo=None, erro=f'Máquina {modelo_id} não encontrada', tipo_maquina=True, tipo_monitor=False)
    except Exception as e:
        return render_template('scan.html', modelo=None, erro=f'Erro: {str(e)}', tipo_maquina=True, tipo_monitor=False)

@app.route('/scan_monitores/<modelo_id>')
def scan_monitores(modelo_id):
    """Página de scan para monitores"""
    try:
        monitor = get_monitor_com_saldo(modelo_id)
        if monitor:
            return render_template('scan.html', modelo=monitor, duplicado=False, tipo_maquina=False, tipo_monitor=True)
        return render_template('scan.html', modelo=None, erro=f'Monitor {modelo_id} não encontrado', tipo_maquina=False, tipo_monitor=True)
    except Exception as e:
        return render_template('scan.html', modelo=None, erro=f'Erro: {str(e)}', tipo_maquina=False, tipo_monitor=True)

@app.route('/usuarios')
@login_required
def usuarios():
    if current_user.role != 'admin':
        flash('Acesso negado: apenas administradores podem gerenciar usuários')
        return redirect(url_for('index'))
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
            users = cur.fetchall()
    
    return render_template('usuarios.html', users=users)

@app.route('/qrcodes')
def galeria_qrcodes():
    """Galeria de QR Codes - Detecta automaticamente se é notebook ou máquina"""
    referrer = request.args.get('tipo', 'notebooks')
    
    if referrer == 'maquinas':
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                               m.localizacao, qr.data_criacao
                        FROM maquinas_modelos m
                        INNER JOIN maquinas_qr_codes qr ON m.id = qr.modelo_id
                        ORDER BY m.marca, m.modelo
                        LIMIT 50
                    ''')
                    
                    qrcodes = []
                    for row in cur.fetchall():
                        qrcodes.append({
                            'id': row[0],
                            'marca': row[1],
                            'modelo': row[2],
                            'processador': row[3] or '',
                            'ram': row[4] or '',
                            'armazenamento': row[5] or '',
                            'localizacao': row[6] or '',
                            'url': f'/api/qr_image_maquinas/{row[0]}',
                            'data': formatar_data_brasil(row[7]) if row[7] else agora_brasil().strftime('%d/%m/%Y %H:%M')
                        })
            
            return render_template('galeria_maquinas.html', qrcodes=qrcodes, tipo='maquinas')
        except Exception as e:
            return render_template('galeria_maquinas.html', qrcodes=[], tipo='maquinas')
    elif referrer == 'monitores':
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT m.id, m.marca, m.modelo, m.tamanho, m.resolucao, m.taxa_refresh,
                               m.tipo_painel, m.localizacao, qr.data_criacao
                        FROM monitores_modelos m
                        INNER JOIN monitores_qr_codes qr ON m.id = qr.modelo_id
                        ORDER BY m.marca, m.modelo
                        LIMIT 50
                    ''')
                    
                    qrcodes = []
                    for row in cur.fetchall():
                        qrcodes.append({
                            'id': row[0],
                            'marca': row[1],
                            'modelo': row[2],
                            'tamanho': row[3] or '',
                            'resolucao': row[4] or '',
                            'taxa_refresh': row[5] or '',
                            'tipo_painel': row[6] or '',
                            'localizacao': row[7] or '',
                            'url': f'/api/qr_image_monitores/{row[0]}',
                            'data': formatar_data_brasil(row[8]) if row[8] else agora_brasil().strftime('%d/%m/%Y %H:%M')
                        })
            
            return render_template('galeria_monitores.html', qrcodes=qrcodes, tipo='monitores')
        except Exception as e:
            return render_template('galeria_monitores.html', qrcodes=[], tipo='monitores')
    else:
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                               qr.data_criacao
                        FROM modelos m
                        INNER JOIN qr_codes qr ON m.id = qr.modelo_id
                        ORDER BY m.marca, m.modelo
                        LIMIT 50
                    ''')
                    
                    qrcodes = []
                    for row in cur.fetchall():
                        qrcodes.append({
                            'id': row[0],
                            'marca': row[1],
                            'modelo': row[2],
                            'processador': row[3] or '',
                            'ram': row[4] or '',
                            'armazenamento': row[5] or '',
                            'url': f'/api/qr_image/{row[0]}',
                            'data': formatar_data_brasil(row[6]) if row[6] else agora_brasil().strftime('%d/%m/%Y %H:%M')
                        })
            
            return render_template('galeria.html', qrcodes=qrcodes, tipo='notebooks')
        except Exception as e:
            return render_template('galeria.html', qrcodes=[], tipo='notebooks')

# ============================================
# API: CADASTRAR MODELO (NOTEBOOK)
# ============================================
@app.route('/api/cadastrar', methods=['POST'])
@login_required
def cadastrar():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem cadastrar modelos'}), 403
    try:
        dados = request.json
        
        if not dados.get('marca') or not dados.get('modelo'):
            return jsonify({'status': 'erro', 'mensagem': 'Preencha marca e modelo'}), 400
        
        marca = dados['marca'][:3].upper().replace(' ', '-')
        modelo_nome = dados['modelo'].replace(' ', '-')[:20]
        processador = dados.get('processador', '').replace(' ', '-')[:15]
        modelo_id = f"{marca}-{modelo_nome}"
        if processador:
            modelo_id += f"-{processador}"
        modelo_id = ''.join(c for c in modelo_id if c.isalnum() or c == '-')
        
        observacao = dados.get('observacao', '').strip()
        data_criacao = agora_brasil().isoformat()
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO modelos (id, marca, modelo, processador, ram, armazenamento, observacao, data_criacao, saldo_atual)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
                    ON CONFLICT (id) DO UPDATE SET
                        marca = EXCLUDED.marca,
                        modelo = EXCLUDED.modelo,
                        processador = EXCLUDED.processador,
                        ram = EXCLUDED.ram,
                        armazenamento = EXCLUDED.armazenamento,
                        observacao = COALESCE(NULLIF(EXCLUDED.observacao, ''), modelos.observacao),
                        data_criacao = EXCLUDED.data_criacao
                    RETURNING (xmax = 0) as is_new
                ''', (modelo_id, dados['marca'], dados['modelo'],
                      dados.get('processador', ''), dados.get('ram', ''),
                      dados.get('armazenamento', ''), observacao,
                      data_criacao))
                
                is_new = cur.fetchone()[0]
        
        mensagem = '✅ Modelo cadastrado!' if is_new else '✅ Modelo atualizado!'
        
        return jsonify({
            'status': 'ok',
            'modelo_id': modelo_id,
            'mensagem': mensagem,
            'atualizado': not is_new,
            'data_criacao': formatar_data_brasil(agora_brasil())
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: CADASTRAR MODELO (MÁQUINAS)
# ============================================
@app.route('/api/cadastrar_maquinas', methods=['POST'])
@login_required
def cadastrar_maquinas():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem cadastrar máquinas'}), 403
    try:
        dados = request.json

        if not dados.get('marca') or not dados.get('modelo'):
            return jsonify({'status': 'erro', 'mensagem': 'Preencha marca e modelo'}), 400

        marca = dados['marca'][:3].upper().replace(' ', '-').strip()
        modelo_nome = dados['modelo'].replace(' ', '-')[:20]
        processador = dados.get('processador', '').replace(' ', '-')[:15]
        modelo_id = f"{marca}-{modelo_nome}"
        if processador:
            modelo_id += f"-{processador}"
        modelo_id = ''.join(c for c in modelo_id if c.isalnum() or c == '-')

        localizacao = (dados.get('localizacao') or '').strip()
        data_criacao = agora_brasil().isoformat()

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO maquinas_modelos (id, marca, modelo, processador, ram, armazenamento, localizacao, data_criacao, saldo_atual)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
                    ON CONFLICT (id) DO UPDATE SET
                        marca = EXCLUDED.marca,
                        modelo = EXCLUDED.modelo,
                        processador = EXCLUDED.processador,
                        ram = EXCLUDED.ram,
                        armazenamento = EXCLUDED.armazenamento,
                        localizacao = COALESCE(NULLIF(EXCLUDED.localizacao, ''), maquinas_modelos.localizacao),
                        data_criacao = EXCLUDED.data_criacao
                    RETURNING (xmax = 0) as is_new
                ''', (
                    modelo_id,
                    dados['marca'],
                    dados['modelo'],
                    dados.get('processador', ''),
                    dados.get('ram', ''),
                    dados.get('armazenamento', ''),
                    localizacao,
                    data_criacao
                ))
                is_new = cur.fetchone()[0]

        mensagem = '✅ Máquina cadastrada!' if is_new else '✅ Máquina atualizada!'

        return jsonify({
            'status': 'ok',
            'modelo_id': modelo_id,
            'mensagem': mensagem,
            'atualizado': not is_new,
            'data_criacao': formatar_data_brasil(agora_brasil())
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: CADASTRAR MODELO (MONITORES)
# ============================================
@app.route('/api/cadastrar_monitores', methods=['POST'])
@login_required
def cadastrar_monitores():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem cadastrar monitores'}), 403
    try:
        dados = request.json

        if not dados.get('marca') or not dados.get('modelo'):
            return jsonify({'status': 'erro', 'mensagem': 'Preencha marca e modelo'}), 400

        marca = dados['marca'][:3].upper().replace(' ', '-').strip()
        modelo_nome = dados['modelo'].replace(' ', '-')[:20]
        tamanho = dados.get('tamanho', '').replace(' ', '-')[:10]
        modelo_id = f"{marca}-{modelo_nome}"
        if tamanho:
            modelo_id += f"-{tamanho}"
        modelo_id = ''.join(c for c in modelo_id if c.isalnum() or c == '-')

        localizacao = (dados.get('localizacao') or '').strip()
        data_criacao = agora_brasil().isoformat()

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO monitores_modelos (id, marca, modelo, tamanho, resolucao, taxa_refresh, tipo_painel, localizacao, data_criacao, saldo_atual)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                    ON CONFLICT (id) DO UPDATE SET
                        marca = EXCLUDED.marca,
                        modelo = EXCLUDED.modelo,
                        tamanho = EXCLUDED.tamanho,
                        resolucao = EXCLUDED.resolucao,
                        taxa_refresh = EXCLUDED.taxa_refresh,
                        tipo_painel = EXCLUDED.tipo_painel,
                        localizacao = COALESCE(NULLIF(EXCLUDED.localizacao, ''), monitores_modelos.localizacao),
                        data_criacao = EXCLUDED.data_criacao
                    RETURNING (xmax = 0) as is_new
                ''', (
                    modelo_id,
                    dados['marca'],
                    dados['modelo'],
                    dados.get('tamanho', ''),
                    dados.get('resolucao', ''),
                    dados.get('taxa_refresh', ''),
                    dados.get('tipo_painel', ''),
                    localizacao,
                    data_criacao
                ))
                is_new = cur.fetchone()[0]

        mensagem = '✅ Monitor cadastrado!' if is_new else '✅ Monitor atualizado!'

        return jsonify({
            'status': 'ok',
            'modelo_id': modelo_id,
            'mensagem': mensagem,
            'atualizado': not is_new,
            'data_criacao': formatar_data_brasil(agora_brasil())
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: GERAR QR CODE (NOTEBOOK)
# ============================================
@app.route('/api/gerar_qr', methods=['POST'])
@login_required
def gerar_qr():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem gerar QR codes'}), 403
    try:
        modelo_id = request.json.get('modelo_id')
        
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, marca, modelo, processador, ram, armazenamento, observacao FROM modelos WHERE id = %s", (modelo_id,))
                modelo = cur.fetchone()
        
        if not modelo:
            return jsonify({'status': 'erro', 'mensagem': 'Modelo não encontrado'}), 404
        
        print(f"🖨️ Gerando etiqueta em NEGRITO para: {modelo[1]} {modelo[2]}")
        
        fontes = carregar_fontes()
        
        label_width = 709
        label_height = 472
        
        label = Image.new('RGB', (label_width, label_height), 'white')
        draw = ImageDraw.Draw(label)
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=1
        )
        qr.add_data(f"{request.host_url}scan/{modelo_id}")
        qr.make(fit=True)
        
        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=SquareModuleDrawer()
        )
        
        qr_size = 200
        qr_resized = qr_img.get_image().resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        
        qr_x = 18
        qr_y = (label_height - qr_size) // 2
        label.paste(qr_resized, (qr_x, qr_y))
        
        draw.rectangle(
            [(qr_x - 5, qr_y - 5), (qr_x + qr_size + 5, qr_y + qr_size + 5)],
            outline='#6c5ce7',
            width=2
        )
        
        draw.line(
            [(qr_x + qr_size + 8, qr_y), (qr_x + qr_size + 8, qr_y + qr_size)],
            fill='#cccccc',
            width=2
        )
        
        x_text = qr_x + qr_size + 15
        y_text = qr_y
        
        nome = f"{modelo[1]} {modelo[2]}".strip()

        nome_font = fontes['nome']
        nome_max_width = label_width - x_text - 18
        max_y_text_end = label_height - 18

        nome_lines = wrap_text(nome, nome_font, nome_max_width, draw)
        line_step_nome = 35
        nome_lines_limited = []
        current_y = y_text
        for ln in nome_lines:
            if current_y + line_step_nome > max_y_text_end:
                break
            nome_lines_limited.append(ln)
            current_y += line_step_nome

        for ln in (nome_lines_limited or ['']):
            draw.text((x_text, y_text), ln, fill='#000000', font=nome_font)
            y_text += line_step_nome

        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#6c5ce7',
            width=2
        )
        y_text += 15

        specs = []
        if modelo[3]:
            specs.append(("Processador:", modelo[3]))
        if modelo[4]:
            specs.append(("RAM:", modelo[4]))
        if modelo[5]:
            specs.append(("Armazenamento:", modelo[5]))
        if modelo[6]:
            specs.append(("Observação:", modelo[6]))
        
        max_text_width = label_width - x_text - 18
        for label_spec, valor in specs:
            draw.text((x_text, y_text), label_spec, fill='#333333', font=fontes['spec_label'])
            y_text += 24

            valor_lines = wrap_text(valor, fontes['spec_valor'], max_text_width, draw)
            for line in valor_lines:
                draw.text((x_text + 10, y_text), line, fill='#000000', font=fontes['spec_valor'])
                y_text += 24

            y_text += 5

        y_text += 8
        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#dddddd',
            width=1
        )
        y_text += 15
        
        buf = io.BytesIO()
        label.save(buf, format='PNG', optimize=True, quality=95)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO qr_codes (modelo_id, imagem_base64, data_criacao)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (modelo_id) DO UPDATE SET
                        imagem_base64 = EXCLUDED.imagem_base64,
                        data_criacao = EXCLUDED.data_criacao
                ''', (modelo_id, img_base64, agora_brasil()))
        
        buf.seek(0)
        
        print(f"✅ QR Code gerado com sucesso: {modelo_id}")
        print(f"📏 Etiqueta: 60mm x 40mm (709x472 px @ 300 DPI)")
        print(f"🔤 Tamanhos de fonte AUMENTADOS: Nome 28px | Labels 24px | Valores 22px | ID 18px | Scan 20px")
        
        return jsonify({
            'status': 'ok',
            'qrcode_url': f'/api/qr_image/{modelo_id}',
            'filepath': f'/api/qr_image/{modelo_id}',
            'mensagem': 'QR Code gerado com sucesso! (Fonte: DejaVuSans-Bold)',
            'data_geracao': formatar_data_brasil(agora_brasil())
        })
        
    except Exception as e:
        print(f"❌ Erro ao gerar QR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: GERAR QR CODE (MÁQUINAS)
# ============================================
@app.route('/api/gerar_qr_maquinas', methods=['POST'])
@login_required
def gerar_qr_maquinas():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem gerar QR codes'}), 403

    try:
        modelo_id = request.json.get('modelo_id')
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT id, marca, modelo, processador, ram, armazenamento, localizacao
                    FROM maquinas_modelos WHERE id = %s
                ''', (modelo_id,))
                modelo = cur.fetchone()

        if not modelo:
            return jsonify({'status': 'erro', 'mensagem': 'Máquina não encontrada'}), 404

        fontes = carregar_fontes()

        label_width = 709
        label_height = 472

        label = Image.new('RGB', (label_width, label_height), 'white')
        draw = ImageDraw.Draw(label)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=1
        )
        qr.add_data(f"{request.host_url}scan_maquinas/{modelo_id}")
        qr.make(fit=True)

        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=SquareModuleDrawer()
        )

        qr_size = 200
        qr_resized = qr_img.get_image().resize((qr_size, qr_size), Image.Resampling.LANCZOS)

        qr_x = 18
        qr_y = (label_height - qr_size) // 2
        label.paste(qr_resized, (qr_x, qr_y))

        draw.rectangle(
            [(qr_x - 5, qr_y - 5), (qr_x + qr_size + 5, qr_y + qr_size + 5)],
            outline='#6c5ce7',
            width=2
        )

        draw.line(
            [(qr_x + qr_size + 8, qr_y), (qr_x + qr_size + 8, qr_y + qr_size)],
            fill='#cccccc',
            width=2
        )

        x_text = qr_x + qr_size + 15
        y_text = qr_y

        nome = f"{modelo[1]} {modelo[2]}".strip()

        nome_font = fontes['nome']
        nome_max_width = label_width - x_text - 18
        max_y_text_end = label_height - 18

        nome_lines = wrap_text(nome, nome_font, nome_max_width, draw)
        line_step_nome = 35
        nome_lines_limited = []
        current_y = y_text
        for ln in nome_lines:
            if current_y + line_step_nome > max_y_text_end:
                break
            nome_lines_limited.append(ln)
            current_y += line_step_nome

        for ln in (nome_lines_limited or ['']):
            draw.text((x_text, y_text), ln, fill='#000000', font=nome_font)
            y_text += line_step_nome

        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#6c5ce7',
            width=2
        )
        y_text += 15

        specs = []
        if modelo[3]:
            specs.append(("Processador:", modelo[3]))
        if modelo[4]:
            specs.append(("RAM:", modelo[4]))
        if modelo[5]:
            specs.append(("Armazenamento:", modelo[5]))
        if modelo[6]:
            specs.append(("Localização:", modelo[6]))

        max_text_width = label_width - x_text - 18
        for label_spec, valor in specs:
            draw.text((x_text, y_text), label_spec, fill='#333333', font=fontes['spec_label'])
            y_text += 24

            valor_lines = wrap_text(valor, fontes['spec_valor'], max_text_width, draw)
            for line in valor_lines:
                draw.text((x_text + 10, y_text), line, fill='#000000', font=fontes['spec_valor'])
                y_text += 24

            y_text += 5

        y_text += 8
        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#dddddd',
            width=1
        )
        y_text += 15

        buf = io.BytesIO()
        label.save(buf, format='PNG', optimize=True, quality=95)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO maquinas_qr_codes (modelo_id, imagem_base64, data_criacao)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (modelo_id) DO UPDATE SET
                        imagem_base64 = EXCLUDED.imagem_base64,
                        data_criacao = EXCLUDED.data_criacao
                ''', (modelo_id, img_base64, agora_brasil()))

        return jsonify({
            'status': 'ok',
            'qrcode_url': f'/api/qr_image_maquinas/{modelo_id}',
            'filepath': f'/api/qr_image_maquinas/{modelo_id}',
            'mensagem': 'QR Code de Máquina gerado com sucesso!',
            'data_geracao': formatar_data_brasil(agora_brasil())
        })

    except Exception as e:
        print(f"❌ Erro ao gerar QR máquinas: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: GERAR QR CODE (MONITORES)
# ============================================
@app.route('/api/gerar_qr_monitores', methods=['POST'])
@login_required
def gerar_qr_monitores():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem gerar QR codes'}), 403

    try:
        modelo_id = request.json.get('modelo_id')
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT id, marca, modelo, tamanho, resolucao, taxa_refresh, tipo_painel, localizacao
                    FROM monitores_modelos WHERE id = %s
                ''', (modelo_id,))
                modelo = cur.fetchone()

        if not modelo:
            return jsonify({'status': 'erro', 'mensagem': 'Monitor não encontrado'}), 404

        fontes = carregar_fontes()

        label_width = 709
        label_height = 472

        label = Image.new('RGB', (label_width, label_height), 'white')
        draw = ImageDraw.Draw(label)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=1
        )
        qr.add_data(f"{request.host_url}scan_monitores/{modelo_id}")
        qr.make(fit=True)

        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=SquareModuleDrawer()
        )

        qr_size = 200
        qr_resized = qr_img.get_image().resize((qr_size, qr_size), Image.Resampling.LANCZOS)

        qr_x = 18
        qr_y = (label_height - qr_size) // 2
        label.paste(qr_resized, (qr_x, qr_y))

        draw.rectangle(
            [(qr_x - 5, qr_y - 5), (qr_x + qr_size + 5, qr_y + qr_size + 5)],
            outline='#6c5ce7',
            width=2
        )

        draw.line(
            [(qr_x + qr_size + 8, qr_y), (qr_x + qr_size + 8, qr_y + qr_size)],
            fill='#cccccc',
            width=2
        )

        x_text = qr_x + qr_size + 15
        y_text = qr_y

        nome = f"{modelo[1]} {modelo[2]}".strip()

        nome_font = fontes['nome']
        nome_max_width = label_width - x_text - 18
        max_y_text_end = label_height - 18

        nome_lines = wrap_text(nome, nome_font, nome_max_width, draw)
        line_step_nome = 35
        nome_lines_limited = []
        current_y = y_text
        for ln in nome_lines:
            if current_y + line_step_nome > max_y_text_end:
                break
            nome_lines_limited.append(ln)
            current_y += line_step_nome

        for ln in (nome_lines_limited or ['']):
            draw.text((x_text, y_text), ln, fill='#000000', font=nome_font)
            y_text += line_step_nome

        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#6c5ce7',
            width=2
        )
        y_text += 15

        specs = []
        if modelo[3]:
            specs.append(("Tamanho:", modelo[3]))
        if modelo[4]:
            specs.append(("Resolução:", modelo[4]))
        if modelo[5]:
            specs.append(("Taxa Refresh:", modelo[5]))
        if modelo[6]:
            specs.append(("Tipo Painel:", modelo[6]))
        if modelo[7]:
            specs.append(("Localização:", modelo[7]))

        max_text_width = label_width - x_text - 18
        for label_spec, valor in specs:
            draw.text((x_text, y_text), label_spec, fill='#333333', font=fontes['spec_label'])
            y_text += 24

            valor_lines = wrap_text(valor, fontes['spec_valor'], max_text_width, draw)
            for line in valor_lines:
                draw.text((x_text + 10, y_text), line, fill='#000000', font=fontes['spec_valor'])
                y_text += 24

            y_text += 5

        y_text += 8
        draw.line(
            [(x_text, y_text), (label_width - 18, y_text)],
            fill='#dddddd',
            width=1
        )
        y_text += 15

        buf = io.BytesIO()
        label.save(buf, format='PNG', optimize=True, quality=95)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO monitores_qr_codes (modelo_id, imagem_base64, data_criacao)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (modelo_id) DO UPDATE SET
                        imagem_base64 = EXCLUDED.imagem_base64,
                        data_criacao = EXCLUDED.data_criacao
                ''', (modelo_id, img_base64, agora_brasil()))

        return jsonify({
            'status': 'ok',
            'qrcode_url': f'/api/qr_image_monitores/{modelo_id}',
            'filepath': f'/api/qr_image_monitores/{modelo_id}',
            'mensagem': 'QR Code de Monitor gerado com sucesso!',
            'data_geracao': formatar_data_brasil(agora_brasil())
        })

    except Exception as e:
        print(f"❌ Erro ao gerar QR monitores: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: SERVIR QR CODE DO BANCO (NOTEBOOK)
# ============================================
@app.route('/api/qr_image/<modelo_id>')
def serve_qr_image(modelo_id):
    """Serve a imagem do QR Code do banco de dados"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT imagem_base64 FROM qr_codes WHERE modelo_id = %s", (modelo_id,))
                result = cur.fetchone()
        
        if result:
            img_data = base64.b64decode(result[0])
            return Response(img_data, mimetype='image/png')
        else:
            return gerar_qr_rapido(modelo_id, 'scan')
    except:
        return gerar_qr_rapido(modelo_id, 'scan')

# ============================================
# API: SERVIR QR CODE DO BANCO (MÁQUINAS)
# ============================================
@app.route('/api/qr_image_maquinas/<modelo_id>')
def serve_qr_image_maquinas(modelo_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT imagem_base64 FROM maquinas_qr_codes WHERE modelo_id = %s", (modelo_id,))
                result = cur.fetchone()

        if result:
            img_data = base64.b64decode(result[0])
            return Response(img_data, mimetype='image/png')

        return gerar_qr_rapido(modelo_id, 'scan_maquinas')

    except Exception:
        return gerar_qr_rapido(modelo_id, 'scan_maquinas')

# ============================================
# API: SERVIR QR CODE DO BANCO (MONITORES)
# ============================================
@app.route('/api/qr_image_monitores/<modelo_id>')
def serve_qr_image_monitores(modelo_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT imagem_base64 FROM monitores_qr_codes WHERE modelo_id = %s", (modelo_id,))
                result = cur.fetchone()

        if result:
            img_data = base64.b64decode(result[0])
            return Response(img_data, mimetype='image/png')

        return gerar_qr_rapido(modelo_id, 'scan_monitores')

    except Exception:
        return gerar_qr_rapido(modelo_id, 'scan_monitores')

def gerar_qr_rapido(modelo_id, prefixo='scan'):
    """QR Code simples para retorno rápido"""
    qr = qrcode.QRCode(version=1, box_size=8, border=1)
    qr.add_data(f"{prefixo}/{modelo_id}")
    qr.make(fit=True)
    img = qr.make_image()
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')

# ============================================
# API: REGENERAR TODOS OS QR CODES
# ============================================
@app.route('/api/regenerate_all_qrs')
@login_required
def regenerate_all_qrs():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem regenerar QR codes'}), 403
    """Regenera todos os QR Codes com a URL atual"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM modelos")
                modelos = cur.fetchall()
        
        regenerados = 0
        for modelo in modelos:
            modelo_id = modelo[0]
            try:
                with app.test_client() as client:
                    response = client.post('/api/gerar_qr', 
                                          json={"modelo_id": modelo_id})
                    if response.status_code == 200:
                        regenerados += 1
            except:
                pass
        
        return jsonify({
            'status': 'ok',
            'mensagem': f'{regenerados} QR Codes regenerados!',
            'url_base': request.host_url,
            'data': formatar_data_brasil(agora_brasil())
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: LISTAR ESTOQUE (NOTEBOOKS)
# ============================================
@app.route('/api/estoque')
def listar_estoque():
    """Lista estoque - Query otimizada"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                        m.observacao,
                        m.data_criacao,
                        COALESCE(SUM(CASE WHEN mov.tipo = 'entrada' THEN mov.quantidade 
                                         ELSE -mov.quantidade END), 0) as saldo,
                        MAX(mov.data) as ultima_movimentacao
                    FROM modelos m
                    LEFT JOIN movimentacoes mov ON m.id = mov.modelo_id
                    GROUP BY m.id
                    ORDER BY m.marca, m.modelo
                    LIMIT 100
                ''')
                
                resultado = []
                for row in cur.fetchall():
                    resultado.append({
                        'id': row[0],
                        'marca': row[1],
                        'modelo': row[2],
                        'processador': row[3] or '',
                        'ram': row[4] or '',
                        'armazenamento': row[5] or '',
                        'observacao': row[6] or '',
                        'data_criacao': row[7],
                        'saldo': row[8],
                        'ultima_movimentacao': formatar_data_brasil(row[9]) if row[9] else 'Nenhuma',
                        'status': '✅ Disponível' if row[8] > 0 else '❌ Zerado'
                    })
        
        return jsonify(resultado)
    except Exception as e:
        return jsonify([])

# ============================================
# API: LISTAR ESTOQUE (MÁQUINAS)
# ============================================
@app.route('/api/estoque_maquinas')
def listar_estoque_maquinas():
    """Lista estoque de máquinas"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                        m.localizacao,
                        m.data_criacao,
                        COALESCE(SUM(CASE WHEN mov.tipo = 'entrada' THEN mov.quantidade 
                                         ELSE -mov.quantidade END), 0) as saldo,
                        MAX(mov.data) as ultima_movimentacao
                    FROM maquinas_modelos m
                    LEFT JOIN maquinas_movimentacoes mov ON m.id = mov.modelo_id
                    GROUP BY m.id
                    ORDER BY m.marca, m.modelo
                    LIMIT 100
                ''')

                resultado = []
                for row in cur.fetchall():
                    resultado.append({
                        'id': row[0],
                        'marca': row[1],
                        'modelo': row[2],
                        'processador': row[3] or '',
                        'ram': row[4] or '',
                        'armazenamento': row[5] or '',
                        'observacao': row[6] or '',
                        'data_criacao': row[7],
                        'saldo': row[8],
                        'ultima_movimentacao': formatar_data_brasil(row[9]) if row[9] else 'Nenhuma',
                        'status': '✅ Disponível' if row[8] > 0 else '❌ Zerado'
                    })

        return jsonify(resultado)
    except Exception:
        return jsonify([])

# ============================================
# API: LISTAR ESTOQUE (MONITORES)
# ============================================
@app.route('/api/estoque_monitores')
def listar_estoque_monitores():
    """Lista estoque de monitores"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        m.id, m.marca, m.modelo, m.tamanho, m.resolucao, m.taxa_refresh, m.tipo_painel,
                        m.localizacao,
                        m.data_criacao,
                        COALESCE(SUM(CASE WHEN mov.tipo = 'entrada' THEN mov.quantidade 
                                         ELSE -mov.quantidade END), 0) as saldo,
                        MAX(mov.data) as ultima_movimentacao
                    FROM monitores_modelos m
                    LEFT JOIN monitores_movimentacoes mov ON m.id = mov.modelo_id
                    GROUP BY m.id
                    ORDER BY m.marca, m.modelo
                    LIMIT 100
                ''')

                resultado = []
                for row in cur.fetchall():
                    resultado.append({
                        'id': row[0],
                        'marca': row[1],
                        'modelo': row[2],
                        'tamanho': row[3] or '',
                        'resolucao': row[4] or '',
                        'taxa_refresh': row[5] or '',
                        'tipo_painel': row[6] or '',
                        'observacao': row[7] or '',
                        'data_criacao': row[8],
                        'saldo': row[9],
                        'ultima_movimentacao': formatar_data_brasil(row[10]) if row[10] else 'Nenhuma',
                        'status': '✅ Disponível' if row[9] > 0 else '❌ Zerado'
                    })

        return jsonify(resultado)
    except Exception:
        return jsonify([])

# ============================================
# API: MOVIMENTAR (ENTRADA/SAÍDA) - NOTEBOOK
# ============================================
@app.route('/api/movimentar', methods=['POST'])
@login_required
def movimentar():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        quantidade = int(dados.get('quantidade', 1))
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id or quantidade < 1:
            return jsonify({'status': 'erro', 'mensagem': 'Dados inválidos'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo < quantidade:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': f'Saldo insuficiente! Disponível: {saldo}',
                            'saldo': saldo
                        }), 400
                
                cur.execute('''
                    INSERT INTO movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING data
                ''', (modelo_id, quantidade, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'SAÍDA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'saldo': novo_saldo,
            'mensagem': f'{emoji} {acao} de {quantidade} unidade(s)!',
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: MOVIMENTAR (ENTRADA/SAÍDA) - MÁQUINAS
# ============================================
@app.route('/api/movimentar_maquinas', methods=['POST'])
@login_required
def movimentar_maquinas():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        quantidade = int(dados.get('quantidade', 1))
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id or quantidade < 1:
            return jsonify({'status': 'erro', 'mensagem': 'Dados inválidos'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, marca, modelo FROM maquinas_modelos WHERE id = %s", (modelo_id,))
                maquina = cur.fetchone()
                if not maquina:
                    return jsonify({'status': 'erro', 'mensagem': 'Máquina não encontrada'}), 404
                
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM maquinas_movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo < quantidade:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': f'Saldo insuficiente! Disponível: {saldo}',
                            'saldo': saldo
                        }), 400
                
                cur.execute('''
                    INSERT INTO maquinas_movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING data
                ''', (modelo_id, quantidade, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM maquinas_movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE maquinas_modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'SAÍDA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'saldo': novo_saldo,
            'mensagem': f'{emoji} {acao} de {quantidade} unidade(s)! Máquina: {maquina[1]} {maquina[2]}',
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: MOVIMENTAR (ENTRADA/SAÍDA) - MONITORES
# ============================================
@app.route('/api/movimentar_monitores', methods=['POST'])
@login_required
def movimentar_monitores():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        quantidade = int(dados.get('quantidade', 1))
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id or quantidade < 1:
            return jsonify({'status': 'erro', 'mensagem': 'Dados inválidos'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, marca, modelo FROM monitores_modelos WHERE id = %s", (modelo_id,))
                monitor = cur.fetchone()
                if not monitor:
                    return jsonify({'status': 'erro', 'mensagem': 'Monitor não encontrado'}), 404
                
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM monitores_movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo < quantidade:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': f'Saldo insuficiente! Disponível: {saldo}',
                            'saldo': saldo
                        }), 400
                
                cur.execute('''
                    INSERT INTO monitores_movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING data
                ''', (modelo_id, quantidade, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM monitores_movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE monitores_modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'SAÍDA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'saldo': novo_saldo,
            'mensagem': f'{emoji} {acao} de {quantidade} unidade(s)! Monitor: {monitor[1]} {monitor[2]}',
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: BIPAR (SCAN RÁPIDO) - NOTEBOOK
# ============================================
@app.route('/api/bipar', methods=['POST'])
@login_required
def bipar():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    """Bipagem ultra rápida para notebooks"""
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo <= 0:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': '❌ Estoque zerado!',
                            'saldo': 0
                        }), 400
                
                cur.execute('''
                    INSERT INTO movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, 1, %s, NOW())
                    RETURNING data
                ''', (modelo_id, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
                
                cur.execute("SELECT * FROM modelos WHERE id = %s", (modelo_id,))
                modelo = cur.fetchone()
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'BAIXA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'mensagem': f'{emoji} {acao}! {modelo[1]} {modelo[2]}',
            'saldo_atual': novo_saldo,
            'tipo': tipo,
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: BIPAR (SCAN RÁPIDO) - MÁQUINAS
# ============================================
@app.route('/api/bipar_maquinas', methods=['POST'])
@login_required
def bipar_maquinas():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    """Bipagem ultra rápida para máquinas"""
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, marca, modelo FROM maquinas_modelos WHERE id = %s", (modelo_id,))
                maquina = cur.fetchone()
                if not maquina:
                    return jsonify({'status': 'erro', 'mensagem': 'Máquina não encontrada'}), 404
                
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM maquinas_movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo <= 0:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': '❌ Estoque zerado!',
                            'saldo': 0
                        }), 400
                
                cur.execute('''
                    INSERT INTO maquinas_movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, 1, %s, NOW())
                    RETURNING data
                ''', (modelo_id, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM maquinas_movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE maquinas_modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'BAIXA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'mensagem': f'{emoji} {acao}! {maquina[1]} {maquina[2]}',
            'saldo_atual': novo_saldo,
            'tipo': tipo,
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: BIPAR (SCAN RÁPIDO) - MONITORES
# ============================================
@app.route('/api/bipar_monitores', methods=['POST'])
@login_required
def bipar_monitores():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem fazer movimentações'}), 403
    """Bipagem ultra rápida para monitores"""
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        tipo = dados.get('tipo', 'saida')
        
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, marca, modelo FROM monitores_modelos WHERE id = %s", (modelo_id,))
                monitor = cur.fetchone()
                if not monitor:
                    return jsonify({'status': 'erro', 'mensagem': 'Monitor não encontrado'}), 404
                
                if tipo == 'saida':
                    cur.execute('''
                        SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                               ELSE -quantidade END), 0)
                        FROM monitores_movimentacoes WHERE modelo_id = %s
                    ''', (modelo_id,))
                    saldo = cur.fetchone()[0]
                    
                    if saldo <= 0:
                        return jsonify({
                            'status': 'erro',
                            'mensagem': '❌ Estoque zerado!',
                            'saldo': 0
                        }), 400
                
                cur.execute('''
                    INSERT INTO monitores_movimentacoes (modelo_id, quantidade, tipo, data)
                    VALUES (%s, 1, %s, NOW())
                    RETURNING data
                ''', (modelo_id, tipo))
                
                data_movimentacao = cur.fetchone()[0]
                
                cur.execute('''
                    SELECT COALESCE(SUM(CASE WHEN tipo = 'entrada' THEN quantidade 
                                           ELSE -quantidade END), 0)
                    FROM monitores_movimentacoes WHERE modelo_id = %s
                ''', (modelo_id,))
                novo_saldo = cur.fetchone()[0]
                
                cur.execute("UPDATE monitores_modelos SET saldo_atual = %s WHERE id = %s", (novo_saldo, modelo_id))
        
        emoji = '📤' if tipo == 'saida' else '📥'
        acao = 'BAIXA' if tipo == 'saida' else 'ENTRADA'
        
        return jsonify({
            'status': 'ok',
            'mensagem': f'{emoji} {acao}! {monitor[1]} {monitor[2]}',
            'saldo_atual': novo_saldo,
            'tipo': tipo,
            'data_movimentacao': formatar_data_brasil(data_movimentacao),
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: REMOVER MODELO (NOTEBOOK)
# ============================================
@app.route('/api/remover', methods=['POST'])
@login_required
def remover():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem remover modelos'}), 403
    """Remove modelo E QR Code automaticamente"""
    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM modelos WHERE id = %s", (modelo_id,))
                modelo = cur.fetchone()
                
                if not modelo:
                    return jsonify({'status': 'erro', 'mensagem': 'Modelo não encontrado'}), 404
                
                cur.execute("DELETE FROM qr_codes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM movimentacoes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM modelos WHERE id = %s", (modelo_id,))
        
        return jsonify({
            'status': 'ok',
            'mensagem': f'✅ Modelo {modelo[1]} {modelo[2]} removido!',
            'data_remocao': formatar_data_brasil(agora_brasil())
        })
        
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: REMOVER MÁQUINAS
# ============================================
@app.route('/api/remover_maquinas', methods=['POST'])
@login_required
def remover_maquinas():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem remover máquinas'}), 403

    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM maquinas_modelos WHERE id = %s", (modelo_id,))
                maquina = cur.fetchone()
                if not maquina:
                    return jsonify({'status': 'erro', 'mensagem': 'Máquina não encontrada'}), 404

                cur.execute("DELETE FROM maquinas_qr_codes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM maquinas_movimentacoes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM maquinas_modelos WHERE id = %s", (modelo_id,))

        return jsonify({'status': 'ok', 'mensagem': f'✅ Máquina removida! ({modelo_id})', 'data_remocao': formatar_data_brasil(agora_brasil())})

    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: REMOVER MONITORES
# ============================================
@app.route('/api/remover_monitores', methods=['POST'])
@login_required
def remover_monitores():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado: apenas administradores podem remover monitores'}), 403

    try:
        dados = request.json
        modelo_id = dados.get('modelo_id')
        if not modelo_id:
            return jsonify({'status': 'erro', 'mensagem': 'ID não informado'}), 400

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM monitores_modelos WHERE id = %s", (modelo_id,))
                monitor = cur.fetchone()
                if not monitor:
                    return jsonify({'status': 'erro', 'mensagem': 'Monitor não encontrado'}), 404

                cur.execute("DELETE FROM monitores_qr_codes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM monitores_movimentacoes WHERE modelo_id = %s", (modelo_id,))
                cur.execute("DELETE FROM monitores_modelos WHERE id = %s", (modelo_id,))

        return jsonify({'status': 'ok', 'mensagem': f'✅ Monitor removido! ({modelo_id})', 'data_remocao': formatar_data_brasil(agora_brasil())})

    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# API: CRIAR USUÁRIO
# ============================================
@app.route('/api/criar_usuario', methods=['POST'])
@login_required
def criar_usuario():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado'}), 403
    
    dados = request.json
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role', 'viewer')
    
    if not username or not password:
        return jsonify({'status': 'erro', 'mensagem': 'Preencha usuário e senha'}), 400
    
    if role not in ['admin', 'viewer']:
        return jsonify({'status': 'erro', 'mensagem': 'Role inválido'}), 400
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                password_hash = generate_password_hash(password)
                cur.execute('''
                    INSERT INTO users (username, password_hash, role)
                    VALUES (%s, %s, %s)
                ''', (username, password_hash, role))
        
        return jsonify({'status': 'ok', 'mensagem': f'Usuário {username} criado com sucesso!'})
    except psycopg2.IntegrityError:
        return jsonify({'status': 'erro', 'mensagem': 'Usuário já existe'}), 400

# ============================================
# API: REMOVER USUÁRIO
# ============================================
@app.route('/api/remover_usuario', methods=['POST'])
@login_required
def remover_usuario():
    if current_user.role != 'admin':
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado'}), 403
    
    dados = request.json
    user_id = dados.get('user_id')
    
    if not user_id or int(user_id) == current_user.id:
        return jsonify({'status': 'erro', 'mensagem': 'Não é possível remover o próprio usuário'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    
    return jsonify({'status': 'ok', 'mensagem': 'Usuário removido com sucesso!'})

# ============================================
# EXPORTAR EXCEL
# ============================================
@app.route('/exportar')
def exportar():
    """Exporta estoque em Excel ordenado por marca"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT m.id, m.marca, m.modelo, m.processador, m.ram, m.armazenamento,
                           COALESCE(SUM(CASE WHEN mov.tipo = 'entrada' THEN mov.quantidade 
                                           ELSE -mov.quantidade END), 0) as saldo,
                           MAX(mov.data) as ultima_movimentacao
                    FROM modelos m
                    LEFT JOIN movimentacoes mov ON m.id = mov.modelo_id
                    GROUP BY m.id, m.marca, m.modelo
                    ORDER BY m.marca ASC, m.modelo ASC
                ''')
                
                dados = [{
                    'Marca': row[1],
                    'Modelo': row[2],
                    'ID': row[0],
                    'Processador': row[3] or 'N/A',
                    'RAM': row[4] or 'N/A',
                    'Armazenamento': row[5] or 'N/A',
                    'Saldo': row[6],
                    'Última Movimentação': formatar_data_brasil(row[7]) if row[7] else 'Nenhuma',
                    'Status': '✅ Disponível' if row[6] > 0 else '❌ Zerado'
                } for row in cur.fetchall()]
        
        import pandas as pd
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df = pd.DataFrame(dados)
            df.to_excel(writer, index=False, sheet_name='Estoque', startrow=1)
            
            workbook = writer.book
            worksheet = writer.sheets['Estoque']
            
            data_exportacao = agora_brasil().strftime('%d/%m/%Y %H:%M:%S')
            worksheet.merge_cells('A1:I1')
            worksheet['A1'] = f'ESTOQUE 4MC - CONTROLE DE NOTEBOOKS (Exportado em: {data_exportacao})'
            worksheet['A1'].font = Font(name='Arial', size=14, bold=True, color='FFFFFF')
            worksheet['A1'].fill = PatternFill(start_color='6C5CE7', end_color='6C5CE7', fill_type='solid')
            worksheet['A1'].alignment = Alignment(horizontal='center', vertical='center')
            
            header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
            header_fill = PatternFill(start_color='6C5CE7', end_color='6C5CE7', fill_type='solid')
            header_alignment = Alignment(horizontal='center', vertical='center')
            
            cell_font = Font(name='Arial', size=10)
            cell_alignment = Alignment(vertical='center')
            
            even_fill = PatternFill(start_color='F8F9FA', end_color='F8F9FA', fill_type='solid')
            odd_fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
            
            thin_border = Border(
                left=Side(style='thin', color='DDDDDD'),
                right=Side(style='thin', color='DDDDDD'),
                top=Side(style='thin', color='DDDDDD'),
                bottom=Side(style='thin', color='DDDDDD')
            )
            
            for col in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=2, column=col)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border
            
            for row_idx in range(3, len(df) + 3):
                for col_idx in range(1, len(df.columns) + 1):
                    cell = worksheet.cell(row=row_idx, column=col_idx)
                    cell.font = cell_font
                    cell.alignment = cell_alignment
                    cell.border = thin_border
                    
                    if row_idx % 2 == 0:
                        cell.fill = even_fill
                    else:
                        cell.fill = odd_fill
                    
                    if col_idx == 9:
                        if cell.value and '✅' in str(cell.value):
                            cell.font = Font(name='Arial', size=10, color='008000', bold=True)
                        elif cell.value and '❌' in str(cell.value):
                            cell.font = Font(name='Arial', size=10, color='FF0000', bold=True)
                    
                    if col_idx == 7 and cell.value == 0:
                        cell.font = Font(name='Arial', size=10, color='FF0000', bold=True)
            
            colunas_largura = {
                'A': 18, 'B': 30, 'C': 25, 'D': 22,
                'E': 15, 'F': 20, 'G': 12, 'H': 25, 'I': 18
            }
            
            for col, width in colunas_largura.items():
                worksheet.column_dimensions[col].width = width
            
            worksheet.row_dimensions[1].height = 35
            worksheet.row_dimensions[2].height = 25
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'estoque_4MC_{agora_brasil().strftime("%Y%m%d_%H%M")}.xlsx'
        )
    except Exception as e:
        print(f"❌ Erro ao exportar: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'erro', 'mensagem': f'Erro ao exportar: {str(e)}'}), 500

# ============================================
# ROTA PARA VERIFICAR TIMEZONE
# ============================================
@app.route('/api/timezone')
def verificar_timezone():
    """Rota para verificar o timezone configurado"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT NOW()")
                hora_banco = cur.fetchone()[0]
                cur.execute("SHOW timezone")
                timezone_banco = cur.fetchone()[0]
        
        return jsonify({
            'status': 'ok',
            'hora_brasil': agora_brasil().strftime('%d/%m/%Y %H:%M:%S'),
            'hora_banco': formatar_data_brasil(hora_banco),
            'timezone_banco': timezone_banco,
            'timezone_aplicacao': 'America/Sao_Paulo'
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ============================================
# INICIAR
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 SISTEMA 4MC - ESTOQUE DE NOTEBOOKS, MÁQUINAS E MONITORES")
    print(f"📱 http://localhost:{port}")
    print("⚡ Banco PostgreSQL + QR Codes")
    print("📐 Ordenação por MARCA no Excel")
    print("📏 Formatação profissional com cores")
    print("🔄 Movimentação para Notebooks, Máquinas e Monitores")
    print(f"🕐 Fuso horário: São Paulo (America/Sao_Paulo)")
    print(f"🕐 Hora atual: {agora_brasil().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)
    app.run(debug=False, host='0.0.0.0', port=port)
