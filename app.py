from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "biblioteca_marista_2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "biblioteca.db")


# ------------------ CONEXÃO E BANCO ------------------ #

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Garante que as tabelas existam e adiciona colunas novas (prateleira, observacao) se faltar."""
    with get_connection() as conn:
        c = conn.cursor()

        # Cria tabela de livros (se não existir)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY,
                titulo TEXT NOT NULL,
                autor TEXT,
                editora TEXT,
                prateleira TEXT,
                ano INTEGER,
                isbn TEXT,
                quantidade_total INTEGER NOT NULL,
                quantidade_disponivel INTEGER NOT NULL,
                observacao TEXT
            );
            """
        )

        # Garante colunas novas em bancos antigos
        c.execute("PRAGMA table_info(livros);")
        cols = [row[1] for row in c.fetchall()]

        if "prateleira" not in cols:
            c.execute("ALTER TABLE livros ADD COLUMN prateleira TEXT;")

        if "observacao" not in cols:
            c.execute("ALTER TABLE livros ADD COLUMN observacao TEXT;")

        # Cria tabela de empréstimos (se não existir)
        c.execute(
            """
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
            );
            """
        )

        conn.commit()


# Inicializa o banco ao subir o app (Render / local)
init_db()


# ------------------ AUXILIARES ------------------ #

def parse_date(date_str: str):
    """Recebe 'yyyy-mm-dd' (do input type=date) e devolve 'yyyy-mm-dd' validado ou None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return None


@app.template_filter("data_br")
def data_br(date_str):
    """Converte 'yyyy-mm-dd' para 'dd/mm/yyyy' para exibir."""
    if not date_str:
        return "-"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return date_str


def get_livros(termo=None):
    """
    Lista livros, já trazendo (se existir) o empréstimo em aberto.
    Usado tanto na página inicial quanto na página 'Livros'.
    """
    with get_connection() as conn:
        c = conn.cursor()
        sql = """
        SELECT l.*,
               e.id AS emprestimo_id,
               e.nome_aluno,
               e.data_prevista_devolucao
          FROM livros l
     LEFT JOIN emprestimos e
            ON l.id = e.livro_id
           AND e.status = 'EM_ABERTO'
        """
        params = []
        if termo:
            sql += """
            WHERE l.titulo LIKE ?
               OR l.autor LIKE ?
               OR l.isbn LIKE ?
               OR l.prateleira LIKE ?
            """
            like = f"%{termo}%"
            params = [like, like, like, like]
        sql += " ORDER BY l.titulo"
        c.execute(sql, params)
        return c.fetchall()


def get_livro(livro_id: int):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM livros WHERE id = ?", (livro_id,))
        return c.fetchone()


def criar_livro(id_manual, titulo, autor, editora, prateleira, observacao, ano, isbn, quantidade):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO livros
                (id, titulo, autor, editora, prateleira, observacao,
                 ano, isbn, quantidade_total, quantidade_disponivel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id_manual, titulo, autor, editora, prateleira, observacao,
             ano, isbn, quantidade, quantidade),
        )
        conn.commit()


def atualizar_livro(livro_id, titulo, autor, editora, prateleira, observacao,
                    ano, isbn, quantidade_total, quantidade_disponivel):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            UPDATE livros
               SET titulo = ?,
                   autor = ?,
                   editora = ?,
                   prateleira = ?,
                   observacao = ?,
                   ano = ?,
                   isbn = ?,
                   quantidade_total = ?,
                   quantidade_disponivel = ?
             WHERE id = ?
            """,
            (titulo, autor, editora, prateleira, observacao,
             ano, isbn, quantidade_total, quantidade_disponivel, livro_id),
        )
        conn.commit()


def excluir_livro_db(livro_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM emprestimos WHERE livro_id = ?", (livro_id,))
        c.execute("DELETE FROM livros WHERE id = ?", (livro_id,))
        conn.commit()


def get_emprestimos_abertos():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, l.titulo AS livro_titulo, l.prateleira
              FROM emprestimos e
              JOIN livros l ON e.livro_id = l.id
             WHERE e.status = 'EM_ABERTO'
             ORDER BY e.data_prevista_devolucao
            """
        )
        return c.fetchall()


def get_emprestimos_atrasados():
    hoje_iso = datetime.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, l.titulo AS livro_titulo, l.prateleira
              FROM emprestimos e
              JOIN livros l ON e.livro_id = l.id
             WHERE e.status = 'EM_ABERTO'
               AND e.data_prevista_devolucao < ?
             ORDER BY e.data_prevista_devolucao
            """,
            (hoje_iso,),
        )
        return c.fetchall()


def get_historico_livro(livro_id, dias=90):
    """Retorna os empréstimos desse livro nos últimos 'dias' (padrão: 90 ~ 3 meses)."""
    limite = datetime.today() - timedelta(days=dias)
    limite_str = limite.strftime("%Y-%m-%d")

    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT *
              FROM emprestimos
             WHERE livro_id = ?
               AND data_emprestimo >= ?
             ORDER BY data_emprestimo DESC
            """,
            (livro_id, limite_str),
        )
        return c.fetchall()


def criar_emprestimo(livro_id, nome_aluno, serie, data_emprestimo, data_prevista):
    with get_connection() as conn:
        c = conn.cursor()

        # se já há empréstimo em aberto para este livro, bloqueia
        c.execute(
            "SELECT COUNT(*) AS qtd FROM emprestimos WHERE livro_id = ? AND status = 'EM_ABERTO'",
            (livro_id,),
        )
        row = c.fetchone()
        if row["qtd"] > 0:
            raise ValueError("Já existe um empréstimo em aberto para este livro.")

        c.execute("SELECT quantidade_disponivel FROM livros WHERE id = ?", (livro_id,))
        livro = c.fetchone()
        if not livro:
            raise ValueError("Livro não encontrado.")
        if livro["quantidade_disponivel"] <= 0:
            raise ValueError("Não há exemplares disponíveis deste livro.")

        c.execute(
            """
            INSERT INTO emprestimos
                (livro_id, nome_aluno, serie, data_emprestimo, data_prevista_devolucao, status)
            VALUES (?, ?, ?, ?, ?, 'EM_ABERTO')
            """,
            (livro_id, nome_aluno, serie, data_emprestimo, data_prevista),
        )

        c.execute(
            "UPDATE livros SET quantidade_disponivel = quantidade_disponivel - 1 WHERE id = ?",
            (livro_id,),
        )

        conn.commit()


def registrar_devolucao(emprestimo_id):
    hoje_iso = datetime.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("SELECT * FROM emprestimos WHERE id = ?", (emprestimo_id,))
        emp = c.fetchone()
        if not emp:
            raise ValueError("Empréstimo não encontrado.")
        if emp["status"] == "DEVOLVIDO":
            raise ValueError("Este empréstimo já está devolvido.")

        livro_id = emp["livro_id"]

        c.execute(
            """
            UPDATE emprestimos
               SET status = 'DEVOLVIDO',
                   data_devolucao = ?
             WHERE id = ?
            """,
            (hoje_iso, emprestimo_id),
        )

        c.execute(
            "UPDATE livros SET quantidade_disponivel = quantidade_disponivel + 1 WHERE id = ?",
            (livro_id,),
        )

        conn.commit()


# ------------------ ROTAS ------------------ #

@app.route("/")
def index():
    # página inicial também faz busca
    termo = request.args.get("q", "").strip()
    livros = get_livros(termo if termo else None)
    return render_template("index.html", livros=livros, termo=termo)


@app.route("/livros")
def listar_livros():
    # página "Livros" = visão detalhada de todos os livros
    livros = get_livros()
    return render_template("livros.html", livros=livros)


@app.route("/livros/novo", methods=["GET", "POST"])
def novo_livro():
    if request.method == "POST":
        id_manual = request.form.get("id", "").strip()
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        editora = request.form.get("editora", "").strip()
        prateleira = request.form.get("prateleira", "").strip()
        observacao = request.form.get("observacao", "").strip()
        ano_str = request.form.get("ano", "").strip()
        isbn = request.form.get("isbn", "").strip()
        qtd_str = request.form.get("quantidade", "").strip()

        if not id_manual or not titulo or not qtd_str:
            flash("ID, título e quantidade são obrigatórios.")
            return redirect(url_for("novo_livro"))

        try:
            ano = int(ano_str) if ano_str else None
        except ValueError:
            ano = None

        try:
            quantidade = int(qtd_str)
            if quantidade <= 0:
                raise ValueError
        except ValueError:
            flash("Quantidade deve ser um número inteiro maior que zero.")
            return redirect(url_for("novo_livro"))

        try:
            criar_livro(int(id_manual), titulo, autor, editora, prateleira,
                        observacao, ano, isbn, quantidade)
            flash("Livro cadastrado com sucesso!")
            return redirect(url_for("listar_livros"))
        except sqlite3.IntegrityError:
            flash("Já existe um livro com esse ID. Escolha outro ID.")
            return redirect(url_for("novo_livro"))

    return render_template("livro_form.html", livro=None)


@app.route("/livros/<int:livro_id>/editar", methods=["GET", "POST"])
def editar_livro(livro_id):
    livro = get_livro(livro_id)
    if not livro:
        flash("Livro não encontrado.")
        return redirect(url_for("listar_livros"))

    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        autor = request.form.get("autor", "").strip()
        editora = request.form.get("editora", "").strip()
        prateleira = request.form.get("prateleira", "").strip()
        observacao = request.form.get("observacao", "").strip()
        ano_str = request.form.get("ano", "").strip()
        isbn = request.form.get("isbn", "").strip()
        qtd_total_str = request.form.get("quantidade_total", "").strip()
        qtd_disp_str = request.form.get("quantidade_disponivel", "").strip()

        try:
            ano = int(ano_str) if ano_str else None
        except ValueError:
            ano = None

        try:
            quantidade_total = int(qtd_total_str)
            quantidade_disponivel = int(qtd_disp_str)
        except ValueError:
            flash("Quantidade total e disponível devem ser números inteiros.")
            return redirect(url_for("editar_livro", livro_id=livro_id))

        atualizar_livro(
            livro_id,
            titulo,
            autor,
            editora,
            prateleira,
            observacao,
            ano,
            isbn,
            quantidade_total,
            quantidade_disponivel,
        )
        flash("Livro atualizado com sucesso!")
        return redirect(url_for("listar_livros"))

    return render_template("livro_form.html", livro=livro)


@app.route("/livros/<int:livro_id>/excluir", methods=["POST"])
def excluir_livro(livro_id):
    excluir_livro_db(livro_id)
    flash("Livro excluído com sucesso!")
    return redirect(url_for("listar_livros"))


@app.route("/livros/<int:livro_id>/historico")
def historico_livro(livro_id):
    livro = get_livro(livro_id)
    if not livro:
        flash("Livro não encontrado.")
        return redirect(url_for("listar_livros"))

    historico = get_historico_livro(livro_id)
    return render_template("historico_livro.html", livro=livro, historico=historico)


@app.route("/emprestimos/abertos")
def emprestimos_abertos():
    emprestimos = get_emprestimos_abertos()
    return render_template("emprestimos_abertos.html", emprestimos=emprestimos)


@app.route("/emprestimos/atrasados")
def emprestimos_atrasados():
    emprestimos = get_emprestimos_atrasados()
    return render_template("emprestimos_atrasados.html", emprestimos=emprestimos)


@app.route("/emprestimos/novo/<int:livro_id>", methods=["GET", "POST"])
def novo_emprestimo(livro_id):
    livro = get_livro(livro_id)
    if not livro:
        flash("Livro não encontrado.")
        return redirect(url_for("listar_livros"))

    if request.method == "POST":
        nome_aluno = request.form.get("nome_aluno", "").strip()
        serie = request.form.get("serie", "").strip()
        data_emp_str = request.form.get("data_emprestimo", "").strip()
        data_prev_str = request.form.get("data_prevista", "").strip()

        if not nome_aluno or not data_emp_str or not data_prev_str:
            flash("Nome do aluno, data de empréstimo e data de devolução são obrigatórios.")
            return redirect(url_for("novo_emprestimo", livro_id=livro_id))

        data_emp_iso = parse_date(data_emp_str)
        data_prev_iso = parse_date(data_prev_str)

        if not data_emp_iso or not data_prev_iso:
            flash("Datas inválidas. Use o seletor de datas.")
            return redirect(url_for("novo_emprestimo", livro_id=livro_id))

        try:
            criar_emprestimo(livro_id, nome_aluno, serie, data_emp_iso, data_prev_iso)
            flash("Empréstimo registrado com sucesso!")
            return redirect(url_for("emprestimos_abertos"))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("novo_emprestimo", livro_id=livro_id))

    return render_template("emprestimo_form.html", livro=livro)


@app.route("/emprestimos/<int:emp_id>/devolver", methods=["POST"])
def devolver_emprestimo(emp_id):
    try:
        registrar_devolucao(emp_id)
        flash("Devolução registrada com sucesso.")
    except ValueError as e:
        flash(str(e))
    return redirect(url_for("emprestimos_abertos"))


if __name__ == "__main__":
    app.run(debug=True)
