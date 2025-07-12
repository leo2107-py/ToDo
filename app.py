import os
import sqlite3
import shutil
from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_from_directory, send_file, g
)
from datetime import datetime, date
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)
DB_FILENAME = 'todo.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
BACKUP_ROOT = 'backups'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_ROOT, exist_ok=True)

def backup_data():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(BACKUP_ROOT, ts)
    os.makedirs(dest, exist_ok=True)
    if os.path.exists(DB_FILENAME):
        shutil.copy2(DB_FILENAME, os.path.join(dest, DB_FILENAME))
    if os.path.isdir(UPLOAD_FOLDER):
        shutil.copytree(UPLOAD_FOLDER, os.path.join(dest, 'uploads'), dirs_exist_ok=True)

def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(DB_FILENAME)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.execute('''
      CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        deadline DATE,
        priority TEXT DEFAULT 'Mittel',
        completed INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        remark TEXT,
        completed_at TIMESTAMP
      )
    ''')
    db.commit()

@app.route('/')
def index():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=0 "
        "ORDER BY (CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), "
        "deadline IS NULL, deadline, created_at DESC"
    ).fetchall()
    tasks = []
    today = date.today()
    for t in rows:
        task = dict(t)
        if task['deadline']:
            dl = datetime.strptime(task['deadline'], '%Y-%m-%d').date()
            task['overdue'] = (dl < today and not task['completed'])
        else:
            task['overdue'] = False
        folder = os.path.join(UPLOAD_FOLDER, str(task['id']))
        task['attachments'] = os.listdir(folder) if os.path.isdir(folder) else []
        tasks.append(task)
    return render_template('index.html', tasks=tasks)

@app.route('/new', methods=['GET','POST'])
def new_task():
    if request.method=='POST':
        db = get_db()
        cur = db.execute(
            'INSERT INTO tasks (text, deadline, priority, remark) VALUES (?,?,?,?)',
            (
                request.form['task'],
                request.form.get('deadline') or None,
                request.form.get('priority','Mittel'),
                request.form.get('remark')
            )
        )
        db.commit()
        task_id = cur.lastrowid
        folder = os.path.join(UPLOAD_FOLDER, str(task_id))
        os.makedirs(folder, exist_ok=True)
        for f in request.files.getlist('attachments'):
            if f and f.filename:
                f.save(os.path.join(folder, f.filename))
        return redirect(url_for('index'))
    return render_template('new.html')

@app.route('/upload/<int:task_id>', methods=['POST'])
def upload(task_id):
    file = request.files.get('file')
    if file and file.filename:
        folder = os.path.join(UPLOAD_FOLDER, str(task_id))
        os.makedirs(folder, exist_ok=True)
        file.save(os.path.join(folder, file.filename))
    return ('',204)

@app.route('/delete-file/<int:task_id>/<path:filename>')
def delete_file(task_id, filename):
    fp = os.path.join(UPLOAD_FOLDER, str(task_id), filename)
    if os.path.exists(fp):
        os.remove(fp)
    return redirect(request.referrer or url_for('index'))

@app.route('/uploads/<int:task_id>/<filename>')
def uploaded_file(task_id, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, str(task_id)), filename)

@app.route('/task/<int:task_id>')
def task_detail(task_id):
    db = get_db()
    t = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not t: return redirect(url_for('index'))
    task = dict(t)
    folder = os.path.join(UPLOAD_FOLDER, str(task_id))
    task['attachments'] = os.listdir(folder) if os.path.isdir(folder) else []
    return render_template('task_detail.html', task=task)

@app.route('/toggle/<int:task_id>')
def toggle(task_id):
    db = get_db()
    row = db.execute('SELECT completed FROM tasks WHERE id=?', (task_id,)).fetchone()
    new_state = 0 if row['completed'] else 1
    if new_state:
        db.execute(
            'UPDATE tasks SET completed=1, archived=1, completed_at=? WHERE id=?',
            (datetime.now(), task_id)
        )
    else:
        db.execute(
            'UPDATE tasks SET completed=0, archived=0, completed_at=NULL WHERE id=?',
            (task_id,)
        )
    db.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['GET','POST'])
def edit(task_id):
    db = get_db()
    if request.method=='POST':
        db.execute(
            'UPDATE tasks SET text=?, deadline=?, priority=?, remark=? WHERE id=?',
            (
                request.form['task'],
                request.form.get('deadline') or None,
                request.form.get('priority','Mittel'),
                request.form.get('remark'),
                task_id
            )
        )
        db.commit()
        folder = os.path.join(UPLOAD_FOLDER, str(task_id))
        os.makedirs(folder, exist_ok=True)
        for f in request.files.getlist('attachments'):
            if f and f.filename:
                f.save(os.path.join(folder, f.filename))
        return redirect(url_for('index'))
    t = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not t: return redirect(url_for('index'))
    task = dict(t)
    folder = os.path.join(UPLOAD_FOLDER, str(task_id))
    attachments = os.listdir(folder) if os.path.isdir(folder) else []
    return render_template('edit.html', task=task, attachments=attachments)

@app.route('/delete/<int:task_id>')
def delete(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    db.commit()
    return redirect(url_for('index'))

@app.route('/archive')
def archive():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=1 "
        "ORDER BY (CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), deadline"
    ).fetchall()
    tasks = []
    for t in rows:
        task = dict(t)
        folder = os.path.join(UPLOAD_FOLDER, str(task['id']))
        task['attachments'] = os.listdir(folder) if os.path.isdir(folder) else []
        tasks.append(task)
    return render_template('archive.html', tasks=tasks)

@app.route('/api/tasks')
def api_tasks():
    db = get_db()
    events = [
        {'id': t['id'], 'title': t['text'], 'start': t['deadline'], 'completed': bool(t['completed'])}
        for t in db.execute('SELECT * FROM tasks WHERE archived=0 AND deadline IS NOT NULL').fetchall()
    ]
    return jsonify(events)

@app.route('/calendar')
def calendar_view():
    return render_template('calendar.html')

@app.route('/export')
def export():
    db = get_db()
    archived = request.args.get('archived')=='1'
    rows = db.execute(
        'SELECT * FROM tasks WHERE archived=? ORDER BY id',
        (1 if archived else 0,)
    ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title='Aufgaben'
    ws.append(['ID','Text','Deadline','Priorität','Bemerkung','Erstellt am','Erledigt am'])
    for r in rows:
        ws.append([
            r['id'], r['text'], r['deadline'] or '',
            r['priority'], r['remark'] or '',
            r['created_at'], r['completed_at'] or ''
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    filename = 'archive.xlsx' if archived else 'tasks.xlsx'
    return send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__=='__main__':
    backup_data()
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
