import os
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime, timedelta, date

import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = "biblioteca_marista_2025"

# --------------------------------------------------------------------
# CONFIGURAÇÃO DO BANCO (Supabase / Postgres)
# --------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "A variável de ambiente DATABASE_URL não está configurada. "
        "Defina-a no Render com a connection string do Supabase."
    )


def get_connection():
    """
    Abre uma conexão com o Postgres (Supabase).
    Usa sslmode=require, que é o padrão do Supabase.
    """
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    return conn


def init_db():
    """
    Garante que as tabelas existam no Postgres.
    Não apaga nada, apenas cria se ainda não existir.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
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

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS emprestimos (
                    id SERIAL PRIMARY KEY,
                    livro_id INTEGER NOT NULL REFERENCES livros(id) ON DELETE CASCADE,
                    nome_aluno TEXT NOT NULL,
                    serie TEXT,
                    data_emprestimo DATE NOT NULL,
                    data_prevista_devolucao DATE NOT NULL,
                    data_devolucao DATE,
                    status TEXT NOT NULL
                );
                """
            )

        conn.commit()


# roda uma vez na subida do app
init_db()

# --------------------------------------------------------------------
# AUXILIARES
# --------------------------------------------------------------------


def parse_date(date_str: str):
    """Recebe 'yyyy-mm-dd' e devolve um objeto date ou None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


@app.template_filter("data_br")
def data_br(value):
    """Converte date/'yyyy-mm-dd' para 'dd/mm/yyyy' na tela."""
    if not value:
        return "-"
    if isinstance(value, (date, datetime)):
        dt = value
    else:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return str(value)
    return dt.strftime("%d/%m/%Y")


def get_livros(termo=None):
    """
    Lista livros, já trazendo (se existir) o empréstimo em aberto.
    Ordena por ID e permite busca também por ID.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
                    WHERE CAST(l.id AS TEXT) ILIKE %s
                       OR l.titulo ILIKE %s
                       OR l.autor ILIKE %s
                       OR l.isbn ILIKE %s
                       OR l.prateleira ILIKE %s
                """
                like = f"%{termo}%"
                params = [like, like, like, like, like]

            sql += " ORDER BY l.id"
            cur.execute(sql, params)
            return cur.fetchall()


def get_livro(livro_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM livros WHERE id = %s", (livro_id,))
            return cur.fetchone()


def criar_livro(id_manual, titulo, autor, editora, prateleira,
                observacao, ano, isbn, quantidade):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO livros
                    (id, titulo, autor, editora, prateleira, observacao,
                     ano, isbn, quantidade_total, quantidade_disponivel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_manual,
                    titulo,
                    autor,
                    editora,
                    prateleira,
                    observacao,
                    ano,
                    isbn,
                    quantidade,
                    quantidade,
                ),
            )
        conn.commit()


def atualizar_livro(livro_id, titulo, autor, editora, prateleira, observacao,
                    ano, isbn, quantidade_total, quantidade_disponivel):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE livros
                   SET titulo = %s,
                       autor = %s,
                       editora = %s,
                       prateleira = %s,
                       observacao = %s,
                       ano = %s,
                       isbn = %s,
                       quantidade_total = %s,
                       quantidade_disponivel = %s
                 WHERE id = %s
                """,
                (
                    titulo,
                    autor,
                    editora,
                    prateleira,
                    observacao,
                    ano,
                    isbn,
                    quantidade_total,
                    quantidade_disponivel,
                    livro_id,
                ),
            )
        conn.commit()


def excluir_livro_db(livro_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # emprestimos tem ON DELETE CASCADE, mas por garantia:
            cur.execute("DELETE FROM emprestimos WHERE livro_id = %s", (livro_id,))
            cur.execute("DELETE FROM livros WHERE id = %s", (livro_id,))
        conn.commit()


def get_emprestimos_abertos():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.*, l.titulo AS livro_titulo, l.prateleira
                  FROM emprestimos e
                  JOIN livros l ON e.livro_id = l.id
                 WHERE e.status = 'EM_ABERTO'
                 ORDER BY e.data_prevista_devolucao
                """
            )
            return cur.fetchall()


def get_emprestimos_atrasados():
    hoje = datetime.today().date()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT e.*, l.titulo AS livro_titulo, l.prateleira
                  FROM emprestimos e
                  JOIN livros l ON e.livro_id = l.id
                 WHERE e.status = 'EM_ABERTO'
                   AND e.data_prevista_devolucao < %s
                 ORDER BY e.data_prevista_devolucao
                """,
                (hoje,),
            )
            return cur.fetchall()


def get_historico_livro(livro_id, dias=90):
    limite = datetime.today().date() - timedelta(days=dias)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                  FROM emprestimos
                 WHERE livro_id = %s
                   AND data_emprestimo >= %s
                 ORDER BY data_emprestimo DESC
                """,
                (livro_id, limite),
            )
            return cur.fetchall()


def criar_emprestimo(livro_id, nome_aluno, serie, data_emprestimo, data_prevista):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # verifica se já existe empréstimo em aberto
            cur.execute(
                """
                SELECT COUNT(*) AS qtd
                  FROM emprestimos
                 WHERE livro_id = %s
                   AND status = 'EM_ABERTO'
                """,
                (livro_id,),
            )
            row = cur.fetchone()
            if row and row["qtd"] > 0:
                raise ValueError("Já existe um empréstimo em aberto para este livro.")

            # verifica disponibilidade
            cur.execute(
                "SELECT quantidade_disponivel FROM livros WHERE id = %s",
                (livro_id,),
            )
            livro = cur.fetchone()
            if not livro:
                raise ValueError("Livro não encontrado.")
            if livro["quantidade_disponivel"] <= 0:
                raise ValueError("Não há exemplares disponíveis deste livro.")

            # cria empréstimo
            cur.execute(
                """
                INSERT INTO emprestimos
                    (livro_id, nome_aluno, serie,
                     data_emprestimo, data_prevista_devolucao, status)
                VALUES (%s, %s, %s, %s, %s, 'EM_ABERTO')
                """,
                (livro_id, nome_aluno, serie, data_emprestimo, data_prevista),
            )

            # atualiza quantidade disponível
            cur.execute(
                """
                UPDATE livros
                   SET quantidade_disponivel = quantidade_disponivel - 1
                 WHERE id = %s
                """,
                (livro_id,),
            )

        conn.commit()


def registrar_devolucao(emprestimo_id):
    hoje = datetime.today().date()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM emprestimos WHERE id = %s",
                (emprestimo_id,),
            )
            emp = cur.fetchone()
            if not emp:
                raise ValueError("Empréstimo não encontrado.")
            if emp["status"] == "DEVOLVIDO":
                raise ValueError("Este empréstimo já está devolvido.")

            livro_id = emp["livro_id"]

            cur.execute(
                """
                UPDATE emprestimos
                   SET status = 'DEVOLVIDO',
                       data_devolucao = %s
                 WHERE id = %s
                """,
                (hoje, emprestimo_id),
            )

            cur.execute(
                """
                UPDATE livros
                   SET quantidade_disponivel = quantidade_disponivel + 1
                 WHERE id = %s
                """,
                (livro_id,),
            )

        conn.commit()


# --------------------------------------------------------------------
# ROTAS
# --------------------------------------------------------------------

@app.route("/")
def index():
    termo = request.args.get("q", "").strip()
    livros = get_livros(termo if termo else None)
    return render_template("index.html", livros=livros, termo=termo)


@app.route("/livros")
def listar_livros():
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
            criar_livro(int(id_manual), titulo, autor, editora,
                        prateleira, observacao, ano, isbn, quantidade)
            flash("Livro cadastrado com sucesso!")
            return redirect(url_for("listar_livros"))
        except psycopg2.errors.UniqueViolation:
            flash("Já existe um livro com esse ID. Escolha outro ID.")
            return redirect(url_for("novo_livro"))
        except Exception as e:
            flash(f"Erro ao cadastrar livro: {e}")
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

        data_emp = parse_date(data_emp_str)
        data_prev = parse_date(data_prev_str)

        if not data_emp or not data_prev:
            flash("Datas inválidas. Use o seletor de datas.")
            return redirect(url_for("novo_emprestimo", livro_id=livro_id))

        try:
            criar_emprestimo(livro_id, nome_aluno, serie, data_emp, data_prev)
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
    # Em desenvolvimento local
    app.run(debug=True)
