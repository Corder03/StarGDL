import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name='estoque_pro.db'):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Inicializa todas as tabelas"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        
        # Tabela de modelos cadastrados
        c.execute('''CREATE TABLE IF NOT EXISTS modelos
                     (id_modelo TEXT PRIMARY KEY,
                      marca TEXT NOT NULL,
                      modelo TEXT NOT NULL,
                      processador TEXT,
                      ram TEXT,
                      armazenamento TEXT,
                      data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Tabela de movimentações (histórico)
        c.execute('''CREATE TABLE IF NOT EXISTS movimentacoes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      id_modelo TEXT NOT NULL,
                      quantidade INTEGER NOT NULL,
                      operacao TEXT NOT NULL,
                      observacao TEXT,
                      data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (id_modelo) REFERENCES modelos(id_modelo))''')
        
        conn.commit()
        conn.close()
    
    def adicionar_modelo(self, dados):
        """Adiciona um novo modelo ao sistema"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO modelos 
                        (id_modelo, marca, modelo, processador, ram, armazenamento)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (dados['id_modelo'], dados['marca'], dados['modelo'],
                      dados.get('processador', ''), dados.get('ram', ''),
                      dados.get('armazenamento', '')))
            conn.commit()
            return True, "Modelo cadastrado com sucesso!"
        except sqlite3.IntegrityError:
            return False, "Modelo já existe!"
        finally:
            conn.close()
    
    def buscar_modelo(self, id_modelo):
        """Busca informações de um modelo"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute("SELECT * FROM modelos WHERE id_modelo=?", (id_modelo,))
        resultado = c.fetchone()
        conn.close()
        
        if resultado:
            return {
                "id_modelo": resultado[0],
                "marca": resultado[1],
                "modelo": resultado[2],
                "processador": resultado[3],
                "ram": resultado[4],
                "armazenamento": resultado[5]
            }
        return None
    
    def listar_modelos(self):
        """Lista todos os modelos"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute("SELECT * FROM modelos ORDER BY marca, modelo")
        modelos = c.fetchall()
        conn.close()
        
        return [{
            "id_modelo": m[0],
            "marca": m[1],
            "modelo": m[2],
            "processador": m[3],
            "ram": m[4],
            "armazenamento": m[5]
        } for m in modelos]
    
    def registrar_movimentacao(self, id_modelo, quantidade, operacao, observacao=""):
        """Registra entrada/saída no estoque"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''INSERT INTO movimentacoes 
                    (id_modelo, quantidade, operacao, observacao)
                    VALUES (?, ?, ?, ?)''',
                 (id_modelo, quantidade, operacao, observacao))
        conn.commit()
        conn.close()
        return True
    
    def verificar_scan_duplicado(self, id_modelo):
        """Verifica se houve scan nos últimos 30 segundos"""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''SELECT data FROM movimentacoes 
                    WHERE id_modelo=? 
                    ORDER BY data DESC LIMIT 1''', (id_modelo,))
        resultado = c.fetchone()
        conn.close()
        
        if resultado:
            ultimo_scan = datetime.strptime(resultado[0], '%Y-%m-%d %H:%M:%S')
            diferenca = (datetime.now() - ultimo_scan).total_seconds()
            return diferenca < 30  # Menos de 30 segundos = duplicado
        return False
    
    def get_estoque_atual(self):
        """Calcula saldo atual de cada modelo"""
        conn = sqlite3.connect(self.db_name)
        
        # Query para calcular saldo
        query = '''
            SELECT 
                m.id_modelo,
                m.marca,
                m.modelo,
                m.processador,
                m.ram,
                m.armazenamento,
                COALESCE(SUM(CASE WHEN mov.operacao = 'entrada' THEN mov.quantidade ELSE -mov.quantidade END), 0) as saldo
            FROM modelos m
            LEFT JOIN movimentacoes mov ON m.id_modelo = mov.id_modelo
            GROUP BY m.id_modelo
            ORDER BY saldo DESC
        '''
        
        df = sqlite3.connect(self.db_name).execute(query).fetchall()
        conn.close()
        
        return [{
            "id_modelo": r[0],
            "marca": r[1],
            "modelo": r[2],
            "processador": r[3],
            "ram": r[4],
            "armazenamento": r[5],
            "saldo": r[6]
        } for r in df]