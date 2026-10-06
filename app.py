import calendar
import sqlite3
from datetime import date

from flask import Flask, render_template, request, redirect, send_from_directory, url_for

app = Flask(__name__)
DB_NAME = 'repertorio_ieav.db'

@app.route('/sw.js')
def sw():
    # Retorna o ficheiro sw.js que está dentro da pasta static
    return send_from_directory(app.static_folder, 'sw.js')

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
         'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS musicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            tom TEXT,
            link TEXT
        )
    ''')
    # Mantida para não perder dados antigos (não é mais usada nas telas)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS listas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            nome TEXT NOT NULL
        )
    ''')
    # NOVO: um repertório agendado em uma data do calendário
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cronograma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,          -- formato AAAA-MM-DD
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL
        )
    ''')
    # NOVO: músicas de cada repertório agendado (ordem preservada)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cronograma_musicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cronograma_id INTEGER NOT NULL,
            musica_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (cronograma_id) REFERENCES cronograma(id) ON DELETE CASCADE,
            FOREIGN KEY (musica_id) REFERENCES musicas(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------- Repertório
@app.route('/')
def index():
    conn = get_db_connection()
    musicas = conn.execute('SELECT * FROM musicas ORDER BY titulo COLLATE NOCASE').fetchall()
    conn.close()
    return render_template('index.html', musicas=musicas)


@app.route('/nova_musica')
def nova_musica():
    return render_template('nova_musica.html')


@app.route('/adicionar_musica', methods=('POST',))
def adicionar_musica():
    titulo = request.form['titulo'].strip()
    tom = request.form.get('tom', '').strip()
    link = request.form.get('link', '').strip()

    if titulo:
        conn = get_db_connection()
        conn.execute('INSERT INTO musicas (titulo, tom, link) VALUES (?, ?, ?)',
                     (titulo, tom, link))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))


@app.route('/editar_musica/<int:id>', methods=('POST',))
def editar_musica(id):
    titulo = request.form['titulo'].strip()
    tom = request.form.get('tom', '').strip()
    link = request.form.get('link', '').strip()

    conn = get_db_connection()
    conn.execute('UPDATE musicas SET titulo = ?, tom = ?, link = ? WHERE id = ?',
                 (titulo, tom, link, id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


@app.route('/deletar_musica/<int:id>', methods=('POST',))
def deletar_musica(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM musicas WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


# ---------------------------------------------------------------- Cronograma
@app.route('/cronograma')
def cronograma():
    hoje = date.today()
    ano = request.args.get('ano', hoje.year, type=int)
    mes = request.args.get('mes', hoje.month, type=int)
    if not 1 <= mes <= 12 or not 1900 <= ano <= 2200:
        ano, mes = hoje.year, hoje.month

    # Semanas começando no domingo
    semanas = calendar.Calendar(firstweekday=6).monthdayscalendar(ano, mes)

    # Mês anterior / próximo
    ano_ant, mes_ant = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    ano_prox, mes_prox = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

    conn = get_db_connection()
    eventos = conn.execute(
        'SELECT * FROM cronograma WHERE data LIKE ? ORDER BY data, id',
        (f'{ano:04d}-{mes:02d}-%',)
    ).fetchall()

    eventos_por_dia = {}
    for ev in eventos:
        musicas = conn.execute('''
            SELECT m.* FROM cronograma_musicas cm
            JOIN musicas m ON m.id = cm.musica_id
            WHERE cm.cronograma_id = ?
            ORDER BY cm.ordem
        ''', (ev['id'],)).fetchall()
        dia = int(ev['data'][8:10])
        eventos_por_dia.setdefault(dia, []).append({
            'id': ev['id'],
            'tipo': ev['tipo'],
            'titulo': ev['titulo'],
            'data': ev['data'],
            'data_br': f"{ev['data'][8:10]}/{ev['data'][5:7]}/{ev['data'][0:4]}",
            'musicas': musicas,
            'musicas_ids': ','.join(str(m['id']) for m in musicas),
        })

    todas_musicas = conn.execute(
        'SELECT * FROM musicas ORDER BY titulo COLLATE NOCASE').fetchall()
    conn.close()

    # Data sugerida para o botão "Adicionar Repertório" (hoje, se estiver no mês exibido)
    if hoje.year == ano and hoje.month == mes:
        data_padrao = hoje.isoformat()
    else:
        data_padrao = f'{ano:04d}-{mes:02d}-01'

    return render_template(
        'cronograma.html',
        data_padrao=data_padrao,
        ano=ano, mes=mes, nome_mes=MESES[mes - 1],
        semanas=semanas, eventos_por_dia=eventos_por_dia,
        todas_musicas=todas_musicas, hoje=hoje,
        ano_ant=ano_ant, mes_ant=mes_ant,
        ano_prox=ano_prox, mes_prox=mes_prox,
    )


@app.route('/cronograma/adicionar', methods=('POST',))
def adicionar_ao_cronograma():
    data = request.form.get('data', '').strip()
    tipo = request.form.get('tipo', 'Semanal')
    titulo = request.form.get('titulo', '').strip()
    ids_musicas = request.form.getlist('musicas')

    try:
        d = date.fromisoformat(data)
    except ValueError:
        return redirect(url_for('cronograma'))

    if not titulo:
        titulo = tipo

    conn = get_db_connection()
    cur = conn.execute('INSERT INTO cronograma (data, tipo, titulo) VALUES (?, ?, ?)',
                       (data, tipo, titulo))
    cronograma_id = cur.lastrowid
    for ordem, musica_id in enumerate(ids_musicas):
        conn.execute(
            'INSERT INTO cronograma_musicas (cronograma_id, musica_id, ordem) VALUES (?, ?, ?)',
            (cronograma_id, int(musica_id), ordem))
    conn.commit()
    conn.close()

    # Volta para o mês da data escolhida
    return redirect(url_for('cronograma', ano=d.year, mes=d.month))


@app.route('/cronograma/editar/<int:id>', methods=('POST',))
def editar_cronograma(id):
    data = request.form.get('data', '').strip()
    tipo = request.form.get('tipo', 'Semanal')
    titulo = request.form.get('titulo', '').strip() or tipo
    ids_musicas = request.form.getlist('musicas')

    try:
        d = date.fromisoformat(data)
    except ValueError:
        return redirect(url_for('cronograma'))

    conn = get_db_connection()
    conn.execute('UPDATE cronograma SET data = ?, tipo = ?, titulo = ? WHERE id = ?',
                 (data, tipo, titulo, id))
    # Recria a lista de músicas na ordem escolhida
    conn.execute('DELETE FROM cronograma_musicas WHERE cronograma_id = ?', (id,))
    for ordem, musica_id in enumerate(ids_musicas):
        conn.execute(
            'INSERT INTO cronograma_musicas (cronograma_id, musica_id, ordem) VALUES (?, ?, ?)',
            (id, int(musica_id), ordem))
    conn.commit()
    conn.close()
    return redirect(url_for('cronograma', ano=d.year, mes=d.month))


@app.route('/cronograma/deletar/<int:id>', methods=('POST',))
def deletar_do_cronograma(id):
    ano = request.form.get('ano', type=int)
    mes = request.form.get('mes', type=int)
    conn = get_db_connection()
    conn.execute('DELETE FROM cronograma_musicas WHERE cronograma_id = ?', (id,))
    conn.execute('DELETE FROM cronograma WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('cronograma', ano=ano, mes=mes))


if __name__ == '__main__':
    app.run(debug=True)