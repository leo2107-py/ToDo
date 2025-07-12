import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__)
DB_FILENAME = 'todo.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
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

@app.route('/upload/<int:task_id>', methods=['POST'])
def upload(task_id):
    file = request.files.get('file')
    if file:
        task_folder = os.path.join(UPLOAD_FOLDER, str(task_id))
        os.makedirs(task_folder, exist_ok=True)
        file.save(os.path.join(task_folder, file.filename))
    return ('', 204)

@app.route('/delete-file/<int:task_id>/<path:filename>')
def delete_file(task_id, filename):
    # lösche Datei vom Dateisystem
    filepath = os.path.join(UPLOAD_FOLDER, str(task_id), filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    # zurück zur Seite, von der gekommen
    return redirect(request.referrer or url_for('index'))

@app.route('/uploads/<int:task_id>/<filename>')
def uploaded_file(task_id, filename):
    return send_from_directory(
        os.path.join(UPLOAD_FOLDER, str(task_id)),
        filename
    )

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            'INSERT INTO tasks (text, deadline, priority, remark) VALUES (?, ?, ?, ?)',
            (
                request.form['task'],
                request.form.get('deadline') or None,
                request.form.get('priority', 'Mittel'),
                request.form.get('remark')
            )
        )
        db.commit()
        return redirect(url_for('index'))

    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=0 ORDER BY "
        "(CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), "
        "deadline IS NULL, deadline, created_at DESC"
    ).fetchall()
    tasks = []
    for t in rows:
        task = dict(t)
        folder = os.path.join(UPLOAD_FOLDER, str(task['id']))
        task['attachments'] = os.listdir(folder) if os.path.isdir(folder) else []
        tasks.append(task)
    return render_template('index.html', tasks=tasks)

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

@app.route('/restore/<int:task_id>')
def restore(task_id):
    db = get_db()
    # zurück auf aktive Liste
    db.execute(
        'UPDATE tasks SET archived=0, completed=0, completed_at=NULL WHERE id=?',
        (task_id,)
    )
    db.commit()
    return redirect(url_for('archive'))

@app.route('/delete/<int:task_id>')
def delete(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    db.commit()
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit(task_id):
    db = get_db()
    if request.method == 'POST':
        db.execute(
            'UPDATE tasks SET text=?, deadline=?, priority=?, remark=? WHERE id=?',
            (
                request.form['task'],
                request.form.get('deadline') or None,
                request.form.get('priority', 'Mittel'),
                request.form.get('remark'),
                task_id
            )
        )
        db.commit()
        return redirect(url_for('index'))
    t = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    task = dict(t)
    folder = os.path.join(UPLOAD_FOLDER, str(task_id))
    attachments = os.listdir(folder) if os.path.isdir(folder) else []
    return render_template('edit.html', task=task, attachments=attachments)

@app.route('/archive')
def archive():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=1 ORDER BY "
        "(CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), deadline"
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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
