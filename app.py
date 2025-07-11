import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__)
DB_FILENAME = 'todo.db'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# DB-Verbindung

def get_db():
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn

# Tabellen anlegen (inkl. remark, completed_at)

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cols = [row['name'] for row in db.execute("PRAGMA table_info(tasks)").fetchall()]
        if 'remark' not in cols:
            db.execute("ALTER TABLE tasks ADD COLUMN remark TEXT")
        if 'completed_at' not in cols:
            db.execute("ALTER TABLE tasks ADD COLUMN completed_at TIMESTAMP")

@app.route('/upload/<int:task_id>', methods=['POST'])
def upload(task_id):
    file = request.files.get('file')
    if file:
        task_folder = os.path.join(UPLOAD_FOLDER, str(task_id))
        os.makedirs(task_folder, exist_ok=True)
        filepath = os.path.join(task_folder, file.filename)
        file.save(filepath)
    return ('', 204)

@app.route('/uploads/<int:task_id>/<filename>')
def uploaded_file(task_id, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, str(task_id)), filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    if request.method == 'POST':
        text = request.form['task']
        deadline = request.form.get('deadline') or None
        priority = request.form.get('priority', 'Mittel')
        remark = request.form.get('remark')
        db.execute(
            'INSERT INTO tasks (text, deadline, priority, remark) VALUES (?, ?, ?, ?)',
            (text, deadline, priority, remark)
        )
        db.commit()
        return redirect(url_for('index'))

    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=0 ORDER BY "
        "(CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), "
        "deadline IS NULL, deadline, created_at DESC"
    ).fetchall()
    tasks_list = []
    for t in rows:
        task = dict(t)
        task_folder = os.path.join(UPLOAD_FOLDER, str(t['id']))
        task['attachments'] = os.listdir(task_folder) if os.path.isdir(task_folder) else []
        tasks_list.append(task)
    return render_template('index.html', tasks=tasks_list)

@app.route('/toggle/<int:task_id>')
def toggle(task_id):
    db = get_db()
    row = db.execute('SELECT completed FROM tasks WHERE id=?', (task_id,)).fetchone()
    new_state = 0 if row['completed'] else 1
    if new_state == 1:
        db.execute(
            'UPDATE tasks SET completed=?, archived=?, completed_at=? WHERE id=?',
            (1, 1, datetime.now(), task_id)
        )
    else:
        db.execute(
            'UPDATE tasks SET completed=?, archived=?, completed_at=NULL WHERE id=?',
            (0, 0, task_id)
        )
    db.commit()
    return redirect(url_for('index'))

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
        text = request.form['task']
        deadline = request.form.get('deadline') or None
        priority = request.form.get('priority', 'Mittel')
        remark = request.form.get('remark')
        db.execute(
            'UPDATE tasks SET text=?, deadline=?, priority=?, remark=? WHERE id=?',
            (text, deadline, priority, remark, task_id)
        )
        db.commit()
        return redirect(url_for('index'))
    task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    attachments = []
    task_folder = os.path.join(UPLOAD_FOLDER, str(task_id))
    if os.path.isdir(task_folder):
        attachments = os.listdir(task_folder)
    return render_template('edit.html', task=task, attachments=attachments)

@app.route('/archive')
def archive():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE archived=1 "
        "ORDER BY (CASE priority WHEN 'Hoch' THEN 1 WHEN 'Mittel' THEN 2 ELSE 3 END), deadline"
    ).fetchall()
    tasks_list = []
    for t in rows:
        task = dict(t)
        folder = os.path.join(UPLOAD_FOLDER, str(t['id']))
        task['attachments'] = os.listdir(folder) if os.path.isdir(folder) else []
        tasks_list.append(task)
    return render_template('archive.html', tasks=tasks_list)

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