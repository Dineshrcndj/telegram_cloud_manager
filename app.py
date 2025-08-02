from flask import Flask, request, render_template, redirect, flash, url_for, session
from flask_session import Session
import requests
from io import BytesIO
import pymysql
import os
app = Flask(__name__)
app.secret_key = 'dinesh_telegram'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Railway DB connection


def get_db_connection():
    return pymysql.connect(
        host='turntable.proxy.rlwy.net',
        port=55455,
        user='root',
        password='NdZzGkmmIKsZPvCUdCJHTiHzOmZXrsMx',
        database='railway',
        cursorclass=pymysql.cursors.Cursor
    )

def create_tables_if_not_exist():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create `tele` table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tele (
            id INT PRIMARY KEY AUTO_INCREMENT,
            phone VARCHAR(10) NOT NULL UNIQUE,
            password VARCHAR(10) NOT NULL,
            bot_token VARCHAR(255) NOT NULL,
            chat_id VARCHAR(10) NOT NULL
        )
    """)

    # Create `files` table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INT PRIMARY KEY AUTO_INCREMENT,
            phone VARCHAR(10),
            folder VARCHAR(20),
            file_id VARCHAR(255),
            filename VARCHAR(100),
            file_path VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
create_tables_if_not_exist()
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(phone) FROM tele WHERE phone = %s', [phone])
        count = cursor.fetchone()[0]
        if count == 1:
            cursor.execute('SELECT password FROM tele WHERE phone = %s', [phone])
            db_password = cursor.fetchone()[0]
            if password == db_password:
                session['phone'] = phone
                cursor.execute('SELECT bot_token, chat_id FROM tele WHERE phone = %s', [phone])
                data = cursor.fetchone()
                session['bot'], session['chat_id'] = data
                cursor.close()
                conn.close()
                return redirect(url_for('index'))
            else:
                cursor.close()
                conn.close()
                return 'password wrong'
        else:
            cursor.close()
            conn.close()
            return 'no login found'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('phone', None)
    session.pop('bot', None)
    session.pop('chat_id', None)
    return redirect(url_for('login'))



@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filename FROM files WHERE id = %s", (file_id,))
        file = cursor.fetchone()

        if file:
            filename = file[0]
            cursor.execute("DELETE FROM files WHERE id = %s", (file_id,))
            conn.commit()
            flash(f"✅ '{filename}' deleted successfully.", "success")
        else:
            flash("❌ File not found.", "error")
    except Exception as e:
        flash(f"❌ Error deleting file: {str(e)}", "error")
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('index'))  # Adjust based on your route



@app.route('/fetchchatit', methods=['GET', 'POST'])
def fetchchatit():
    if request.method == 'POST':
        bot_token = request.form['bot_token']
        TELEGRAM_API_URL = f'https://api.telegram.org/bot{bot_token}/getUpdates'
        response = requests.get(TELEGRAM_API_URL)
        if response.ok:
            data = response.json()
            if data['result']:
                chat_id = data['result'][0]['message']['chat']['id']
                session['bottoken'] = bot_token
                session['chat_idfrombot'] = chat_id
                return redirect(url_for('signup'))
            else:
                return 'No messages found. Please send a message to your bot first.'
        else:
            return 'Failed to fetch updates. Please check your bot token.'
    return render_template('fetchchatit.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        bot_token = request.form['bot_token']
        chat_id = request.form['chat_id']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(phone) FROM tele WHERE phone = %s', [phone])
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute(
                'INSERT INTO tele (phone, password, bot_token, chat_id) VALUES (%s, %s, %s, %s)',
                [phone, password, bot_token, chat_id]
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('login'))
        else:
            cursor.close()
            conn.close()
            return 'phone already exists'
    return render_template('signup.html')

@app.route('/index', methods=['GET', 'POST'])
def index():
    file_responses = []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT folder, file_id, file_path, filename, folder FROM files WHERE phone = %s', [session['phone']])
    session['files'] = cursor.fetchall()
    
    cursor.execute('SELECT DISTINCT folder FROM files where phone = %s', [session['phone']])
    folders = cursor.fetchall()
    session['folders'] = [i[0] for i in folders]

    cursor.execute('SELECT * FROM files WHERE phone = %s ORDER BY created_at DESC LIMIT 5', [session['phone']])
    recent = cursor.fetchall()
    
    cursor.close()
    conn.close()

    if request.method == 'POST':
        files = request.files.getlist('files')
        folder = request.form['folder']
        if not folder:
            folder = request.form.get('foldername', '').strip() or None
        conn = get_db_connection()
        cursor = conn.cursor()

        for file in files:
            file_stream = BytesIO(file.read())
            file_stream.name = file.filename
            TELEGRAM_API_URL = f'https://api.telegram.org/bot{session["bot"]}/sendDocument'
            response = requests.post(TELEGRAM_API_URL, data={
                'chat_id': session['chat_id'],
            }, files={
                'document': (file.filename, file_stream)
            })

            if response.ok:
                telegram_file_id = response.json()['result']['document']['file_id']
                file_path_resp = requests.post(f'https://api.telegram.org/bot{session["bot"]}/getFile?file_id={telegram_file_id}')
                telegram_file_path = file_path_resp.json()['result']['file_path']
                folder = folder or 'null'
                cursor.execute(
                    'INSERT INTO files (phone, folder, file_id, file_path, filename) VALUES (%s, %s, %s, %s, %s)',
                    [session['phone'], folder, telegram_file_id, telegram_file_path, file.filename]
                )
                conn.commit()
                file_responses.append((file.filename, telegram_file_id, telegram_file_path, None))
            else:
                file_responses.append((file.filename, None, response.text))
        
        cursor.close()
        conn.close()

    return render_template('index.html', file_responses=file_responses, recent=recent)

@app.route('/filterfolder', methods=['GET', 'POST'])
def filterfolder():
    if request.method == 'POST':
        folder = request.form['foldervalue']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM files WHERE folder = %s AND phone = %s ORDER BY created_at DESC', [folder, session['phone']])
        session['folderdata'] = cursor.fetchall()
        cursor.close()
        conn.close()
    return redirect(url_for('index'))



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
