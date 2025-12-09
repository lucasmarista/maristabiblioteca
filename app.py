from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "biblioteca_marista_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "biblioteca.db")


# ---------------- BANCO DE DADOS ---------------- #

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS livros (
            id INTEGER PRIMARY KEY,
            titulo TEXT NOT NULL,
            autor TEXT,
            editora TEXT,
            ano INTEGER,
            isbn TEXT,
            quantidade_total INTEGER NOT NULL,
            quantidade_disponivel INTEGER NOT NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS emprestimos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            livro_id INTEGER NOT NULL,
            nome_aluno TEXT NOT NULL,
            serie TEXT,
            data_emprestimo TEXT NOT NULL,
            data_prevista_devolucao TEXT NOT NULL,
            data_devolucao TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY(livro_id) REFERENCES livros(id)
        )
        """)

        conn.commit()


init_db()


# ---------------- FUNÇÕES AUXILIARES ---------------- #

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except:
        return None


@app.template_filter("data_br")
def data_br(date_str):
    if not date_str:
        return "-"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return date_str


# ---------------- ROTAS ---------------- #

@app.route("/")
def index():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
        SELECT l.*, e.nome_aluno, e.data_prevista_devolucao, e.status
        FROM livros l
        LEFT JOIN emprestimos e ON l.id = e.livro_id AND e.status = 'EM_ABERTO'
        ORDER BY l.titulo
        """)
        livros = c.fetchall()
    return render_template("index.html", livros=livros)


# ----- Cadastrar novo livro ----- #
@app.route("/livros/novo", methods=["GET", "POST"])
def novo_livro():
    if request.method == "POST":
        id_manual = request.form["id"].strip()
        titulo = request.form["titulo"].strip()
        autor = request.form["autor"].strip()
        editora = request.form["editora"].strip()
        ano = request.form["ano"].strip()
        isbn = request.form["isbn"].strip()
        quantidade = request.form["quantidade"].strip()

        if not id_manual or not titulo or not quantidade:
            flash("Preencha todos os campos obrigatórios.")
            return redirect(url_for("novo_livro"))

        with get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute("""
                INSERT INTO livros (id, titulo, autor, editora, ano, isbn, quantidade_total, quantidade_disponivel)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (id_manual, titulo, autor, editora, ano, isbn, quantidade, quantidade))
                conn.commit()
                flash("Livro cadastrado com sucesso!")
            except sqlite3.IntegrityError:
                flash("Já existe um livro com este ID.")

        return redirect(url_for("index"))
    return render_template("livro_form.html")


# ----- Editar ou Excluir livro ----- #
@app.route("/livros/<int:livro_id>/editar", methods=["GET", "POST"])
def editar_livro(livro_id):
    with get_connection() as conn:
        c = conn.cursor()
        if request.method == "POST":
            titulo = request.form["titulo"]
            autor = request.form["autor"]
            editora = request.form["editora"]
            ano = request.form["ano"]
            isbn = request.form["isbn"]
            quantidade_total = request.form["quantidade_total"]
            quantidade_disponivel = request.form["quantidade_disponivel"]

            c.execute("""
                UPDATE livros SET
                    titulo=?, autor=?, editora=?, ano=?, isbn=?, quantidade_total=?, quantidade_disponivel=?
                WHERE id=?
            """, (titulo, autor, editora, ano, isbn, quantidade_total, quantidade_disponivel, livro_id))
            conn.commit()
            flash("Livro atualizado com sucesso!")
            return redirect(url_for("index"))

        c.execute("SELECT * FROM livros WHERE id=?", (livro_id,))
        livro = c.fetchone()
    return render_template("livro_edit.html", livro=livro)


@app.route("/livros/<int:livro_id>/excluir", methods=["POST"])
def excluir_livro(livro_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM livros WHERE id=?", (livro_id,))
        conn.commit()
    flash("Livro excluído com sucesso!")
    return redirect(url_for("index"))


# ----- Empréstimos ----- #
@app.route("/livros/<int:livro_id>/emprestar", methods=["GET", "POST"])
def emprestar(livro_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM livros WHERE id=?", (livro_id,))
        livro = c.fetchone()

        if request.method == "POST":
            nome_aluno = request.form["nome_aluno"].strip()
            serie = request.form["serie"].strip()
            data_emprestimo = parse_date(request.form["data_emprestimo"])
            data_prevista = parse_date(request.form["data_prevista"])

            if not nome_aluno or not data_emprestimo or not data_prevista:
                flash("Preencha todos os campos obrigatórios.")
                return redirect(url_for("emprestar", livro_id=livro_id))

            c.execute("""
                INSERT INTO emprestimos (livro_id, nome_aluno, serie, data_emprestimo, data_prevista_devolucao, status)
                VALUES (?, ?, ?, ?, ?, 'EM_ABERTO')
            """, (livro_id, nome_aluno, serie, data_emprestimo, data_prevista))

            c.execute("UPDATE livros SET quantidade_disponivel = quantidade_disponivel - 1 WHERE id=?", (livro_id,))
            conn.commit()
            flash("Empréstimo registrado com sucesso!")
            return redirect(url_for("index"))

    return render_template("emprestimo_form.html", livro=livro)


@app.route("/emprestimos/<int:livro_id>/devolver", methods=["POST"])
def devolver(livro_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE emprestimos
               SET status='DEVOLVIDO', data_devolucao=?
             WHERE livro_id=? AND status='EM_ABERTO'
        """, (datetime.now().strftime("%Y-%m-%d"), livro_id))
        c.execute("UPDATE livros SET quantidade_disponivel = quantidade_disponivel + 1 WHERE id=?", (livro_id,))
        conn.commit()
    flash("Livro devolvido com sucesso!")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
