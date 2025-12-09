from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

# troque por algo mais difícil se quiser mais segurança
app.secret_key = "biblioteca_marista_super_secret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "biblioteca.db")


# ------------------ BANCO DE DADOS ------------------ #

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # acessar colunas por nome
    return conn


def init_db():
    """Cria as tabelas, se ainda não existirem."""
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT,
                ano INTEGER,
                isbn TEXT,
                quantidade_total INTEGER NOT NULL,
                quantidade_disponivel INTEGER NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                contato TEXT
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS emprestimos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                livro_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                data_emprestimo TEXT NOT NULL,
                data_prevista_devolucao TEXT NOT NULL,
                data_devolucao TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY(livro_id) REFERENCES livros(id),
                FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
            );
        """)

        conn.commit()


# ------------------ FUNÇÕES AUXILIARES ------------------ #

def parse_data_br(data_str):
    """Recebe 'dd/mm/aaaa' e devolve 'aaaa-mm-dd'. Retorna None se inválida."""
    try:
        dt = datetime.strptime(data_str.strip(), "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def format_data_iso(data_iso):
    """Recebe 'aaaa-mm-dd' e devolve 'dd/mm/aaaa'."""
    if not data_iso:
        return ""
    try:
        dt = datetime.strptime(data_iso, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return data_iso


@app.template_filter("data_br")
def filtro_data_br(value):
    return format_data_iso(value)


# ------------------ LIVROS ------------------ #

def get_livros(termo_busca=None):
    with get_connection() as conn:
        cur = conn.cursor()
        if termo_busca:
            like = f"%{termo_busca}%"
            cur.execute("""
                SELECT * FROM livros
                WHERE titulo LIKE ?
                   OR autor  LIKE ?
                   OR isbn   LIKE ?
                ORDER BY titulo
            """, (like, like, like))
        else:
            cur.execute("SELECT * FROM livros ORDER BY titulo")
        return cur.fetchall()


def criar_livro(titulo, autor, ano, isbn, quantidade):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO livros
                (titulo, autor, ano, isbn, quantidade_total, quantidade_disponivel)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (titulo, autor or None, ano, isbn or None, quantidade, quantidade))
        conn.commit()


# ------------------ USUÁRIOS (LEITORES) ------------------ #

def get_usuarios():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios ORDER BY nome")
        return cur.fetchall()


def criar_usuario(nome, contato):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO usuarios (nome, contato)
            VALUES (?, ?)
        """, (nome, contato or None))
        conn.commit()


# ------------------ EMPRÉSTIMOS ------------------ #

def get_emprestimos_abertos():
    """Retorna lista de tuplas (emprestimo_row, atrasado_bool)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.*, l.titulo AS livro_titulo, u.nome AS usuario_nome
              FROM emprestimos e
              JOIN livros l   ON e.livro_id   = l.id
              JOIN usuarios u ON e.usuario_id = u.id
             WHERE e.status = 'EM_ABERTO'
             ORDER BY e.data_prevista_devolucao
        """)
        emprestimos = cur.fetchall()

    hoje_iso = datetime.today().strftime("%Y-%m-%d")
    lista = []
    for e in emprestimos:
        atrasado = e["data_prevista_devolucao"] < hoje_iso
        lista.append((e, atrasado))
    return lista


def get_emprestimos_atrasados():
    hoje_iso = datetime.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.*, l.titulo AS livro_titulo, u.nome AS usuario_nome
              FROM emprestimos e
              JOIN livros l   ON e.livro_id   = l.id
              JOIN usuarios u ON e.usuario_id = u.id
             WHERE e.status = 'EM_ABERTO'
               AND e.data_prevista_devolucao < ?
             ORDER BY e.data_prevista_devolucao
        """, (hoje_iso,))
        return cur.fetchall()


def criar_emprestimo(livro_id, usuario_id, data_prevista_iso):
    hoje_iso = datetime.today().strftime("%Y-%m-%d")

    with get_connection() as conn:
        cur = conn.cursor()

        # verifica livro
        cur.execute("SELECT * FROM livros WHERE id = ?", (livro_id,))
        livro = cur.fetchone()
        if not livro:
            raise ValueError("Livro não encontrado.")
        if livro["quantidade_disponivel"] <= 0:
            raise ValueError("Não há exemplares disponíveis para este livro.")

        # verifica usuário
        cur.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
        usuario = cur.fetchone()
        if not usuario:
            raise ValueError("Leitor não encontrado.")

        # registra empréstimo
        cur.execute("""
            INSERT INTO emprestimos
                (livro_id, usuario_id, data_emprestimo, data_prevista_devolucao, status)
            VALUES (?, ?, ?, ?, 'EM_ABERTO')
        """, (livro_id, usuario_id, hoje_iso, data_prevista_iso))

        # atualiza estoque
        cur.execute("""
            UPDATE livros
               SET quantidade_disponivel = quantidade_disponivel - 1
             WHERE id = ?
        """, (livro_id,))

        conn.commit()


def registrar_devolucao(emprestimo_id):
    hoje_iso = datetime.today().strftime("%Y-%m-%d")

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT * FROM emprestimos WHERE id = ?", (emprestimo_id,))
        emp = cur.fetchone()
        if not emp:
            raise ValueError("Empréstimo não encontrado.")

        if emp["status"] == "DEVOLVIDO":
            raise ValueError("Este empréstimo já foi devolvido.")

        livro_id = emp["livro_id"]

        # atualiza empréstimo
        cur.execute("""
            UPDATE emprestimos
               SET status = 'DEVOLVIDO',
                   data_devolucao = ?
             WHERE id = ?
        """, (hoje_iso, emprestimo_id))

        # devolve exemplar ao estoque
        cur.execute("""
            UPDATE livros
               SET quantidade_disponivel = quantidade_disponivel + 1
             WHERE id = ?
        """, (livro_id,))

        conn.commit()


# ------------------ INICIALIZAÇÃO ------------------ #

@app.before_first_request
def inicializar():
    init_db()


# ------------------ ROTAS ------------------ #

@app.route("/")
def index():
    livros = get_livros()
    usuarios = get_usuarios()
    atrasados = get_emprestimos_atrasados()
    return render_template(
        "index.html",
        total_livros=len(livros),
        total_usuarios=len(usuarios),
        total_atrasados=len(atrasados),
        atrasados=atrasados,
    )


# ----- Livros ----- #

@app.route("/livros")
def listar_livros():
    termo = request.args.get("q", "").strip()
    livros = get_livros(termo if termo else None)
    return render_template("livros.html", livros=livros, termo=termo)


@app.route("/livros/novo", methods=["GET", "POST"])
def novo_livro():
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        ano_str = request.form.get("ano", "").strip()
        isbn = request.form.get("isbn", "").strip()
        qtd_str = request.form.get("quantidade", "").strip()

        if not titulo:
            flash("Título é obrigatório.")
            return redirect(url_for("novo_livro"))

        ano = int(ano_str) if ano_str.isdigit() else None

        if not qtd_str.isdigit() or int(qtd_str) <= 0:
            flash("Quantidade deve ser um número inteiro maior que zero.")
            return redirect(url_for("novo_livro"))

        qtd = int(qtd_str)
        criar_livro(titulo, autor, ano, isbn, qtd)
        flash("Livro cadastrado com sucesso!")
        return redirect(url_for("listar_livros"))

    return render_template("livro_form.html")


# ----- Usuários ----- #

@app.route("/usuarios")
def listar_usuarios():
    usuarios = get_usuarios()
    return render_template("usuarios.html", usuarios=usuarios)


@app.route("/usuarios/novo", methods=["GET", "POST"])
def novo_usuario():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        contato = request.form.get("contato", "").strip()

        if not nome:
            flash("Nome é obrigatório.")
            return redirect(url_for("novo_usuario"))

        criar_usuario(nome, contato)
        flash("Leitor cadastrado com sucesso!")
        return redirect(url_for("listar_usuarios"))

    return render_template("usuario_form.html")


# ----- Empréstimos ----- #

@app.route("/emprestimos/abertos")
def emprestimos_abertos():
    emprestimos = get_emprestimos_abertos()
    return render_template("emprestimos_abertos.html", emprestimos=emprestimos)


@app.route("/emprestimos/atrasados")
def emprestimos_atrasados():
    emprestimos = get_emprestimos_atrasados()
    return render_template("emprestimos_atrasados.html", emprestimos=emprestimos)


@app.route("/emprestimos/novo", methods=["GET", "POST"])
def novo_emprestimo():
    if request.method == "POST":
        livro_id_str = request.form.get("livro_id", "").strip()
        usuario_id_str = request.form.get("usuario_id", "").strip()
        data_prevista_str = request.form.get("data_prevista", "").strip()

        if not (livro_id_str.isdigit() and usuario_id_str.isdigit()):
            flash("Livro e leitor são obrigatórios.")
            return redirect(url_for("novo_emprestimo"))

        data_prevista_iso = parse_data_br(data_prevista_str)
        if not data_prevista_iso:
            flash("Data prevista inválida. Use o formato dd/mm/aaaa.")
            return redirect(url_for("novo_emprestimo"))

        try:
            criar_emprestimo(int(livro_id_str), int(usuario_id_str), data_prevista_iso)
            flash("Empréstimo registrado com sucesso!")
            return redirect(url_for("emprestimos_abertos"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("novo_emprestimo"))

    livros = [l for l in get_livros() if l["quantidade_disponivel"] > 0]
    usuarios = get_usuarios()
    return render_template("emprestimo_form.html", livros=livros, usuarios=usuarios)


@app.route("/emprestimos/<int:emp_id>/devolver", methods=["POST"])
def devolver_emprestimo(emp_id):
    try:
        registrar_devolucao(emp_id)
        flash("Devolução registrada com sucesso.")
    except ValueError as e:
        flash(str(e))

    return redirect(url_for("emprestimos_abertos"))


if __name__ == "__main__":
    # Para rodar localmente:
    app.run(debug=True)
