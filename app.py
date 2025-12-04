# --- 這是【新舊功能完美融合版】app.py ---
import os
import json
import random
import shutil
import requests
import glob
import threading
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from mutagen.mp3 import MP3
from moviepy.editor import *
import moviepy.editor as mpe 
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# --- 資料庫設定 ---
database_url = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- 資料庫模型 ---
# --- 資料庫模型 (Models) ---

# 1. 使用者表
class User(UserMixin, db.Model):
    # ★★★ 關鍵修改：指定獨一無二的資料表名稱 ★★★
    __tablename__ = 'rhythm_users' 
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    # 注意：這裡的 relationship 不需要改，它是在 Python 層面的關聯
    workouts = db.relationship('Workout', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 2. 運動紀錄表
class Workout(db.Model):
    # ★★★ 關鍵修改：指定獨一無二的資料表名稱 ★★★
    __tablename__ = 'rhythm_workouts'
    
    id = db.Column(db.Integer, primary_key=True)
    # 注意：ForeignKey 必須指向 '資料表名稱.id'，所以這裡要改成新的表名
    user_id = db.Column(db.Integer, db.ForeignKey('rhythm_users.id'), nullable=False)
    
    song_name = db.Column(db.String(200), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Integer, default=5)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- 基本設定 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
VIDEO_FOLDER = os.path.join(BASE_DIR, 'static', 'videos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)

def clean_temp_files():
    for f in glob.glob("temp_*.gif"):
        try: os.remove(f)
        except: pass
clean_temp_files()

try:
    with open('static/data/actions.json', 'r', encoding='utf-8') as f:
        ACTIONS = json.load(f)
except Exception as e:
    ACTIONS = {}

progress_store = {} 

# --- 認證路由 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('登入失敗，請檢查帳號密碼', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('該帳號已被註冊', 'error')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- API 路由 ---
@app.route('/api/save_workout', methods=['POST'])
@login_required
def save_workout():
    data = request.get_json()
    new_workout = Workout(
        user_id=current_user.id,
        song_name=data.get('songName', '未知歌曲'),
        duration=data.get('duration', 0),
        rating=data.get('rating', 5)
    )
    db.session.add(new_workout)
    db.session.commit()
    return jsonify({"status": "success", "message": "紀錄已儲存"})

@app.route('/api/get_history', methods=['GET'])
@login_required
def get_history():
    workouts = Workout.query.filter_by(user_id=current_user.id).order_by(Workout.date_posted.desc()).all()
    data = []
    for w in workouts:
        data.append({
            "songName": w.song_name,
            "duration": w.duration,
            "rating": w.rating,
            "date": w.date_posted.strftime("%Y/%m/%d %H:%M")
        })
    return jsonify(data)

# --- 主應用路由 ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', username=current_user.username)

@app.route('/upload_analyze', methods=['POST'])
@login_required
def upload_analyze():
    # 接收首頁的上傳與設定
    if 'music_file' not in request.files:
        return "未上傳檔案", 400
    
    file = request.files['music_file']
    if file.filename == '':
        return "未選擇檔案", 400

    filename = file.filename
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    difficulty = request.form.get('difficulty', 'low')
    try:
        duration = float(request.form.get('duration', 5))
    except:
        duration = 5.0
        
    target_seconds = duration * 60

    # 1. 處理音樂
    music_list = [{'name': filename, 'duration': 180}] 
    try:
        audio = MP3(path)
        music_list[0]['duration'] = int(audio.info.length)
    except:
        pass

    # 2. 處理動作 (關鍵修改：優先使用前端傳來的選單)
    actions_list_raw = request.form.getlist('actions')
    actions_data = []
    
    if actions_list_raw:
        # A. 使用者有手動勾選
        for action_str in actions_list_raw:
            if "|" in action_str:
                section, name = action_str.split("|")
                section = section.strip()
                name = name.strip()
                found_action = next((item for item in ACTIONS.get(section, {}).get(difficulty, []) if item['name'] == name), None)
                if found_action:
                    actions_data.append({"name": name, "gif_url": found_action.get("gif_url")})
                else:
                    actions_data.append({"name": name, "gif_url": None})
    else:
        # B. 使用者沒勾選 -> 自動隨機配對 (並補回 list_raw 供顯示)
        actions_list_raw = []
        for section in ['warmup', 'core', 'cooldown']:
            candidates = ACTIONS.get(section, {}).get(difficulty, [])
            if candidates:
                selected = random.sample(candidates, k=min(len(candidates), 3))
                for item in selected:
                    actions_data.append({
                        "name": item['name'], 
                        "gif_url": item.get('gif_url')
                    })
                    actions_list_raw.append(f"{section}|{item['name']}")

    # 準備資料包
    form_data = {
        "difficulty": difficulty,
        "duration": duration,
        "music_list": music_list,
        "actions": actions_list_raw, # 現在這裡一定有值了！
        "actions_data": actions_data
    }

    return render_template('music-analysis.html', form_data_json=json.dumps(form_data, ensure_ascii=False))

@app.route('/upload', methods=['POST'])
def upload_files():
    return jsonify({"uploaded": []})

@app.route('/get_actions')
def get_actions():
    section = request.args.get('section', 'warmup')
    level = request.args.get('level', 'low')
    if section in ACTIONS and level in ACTIONS[section]:
        return jsonify(ACTIONS[section][level])
    return jsonify([])

@app.route('/compose', methods=['POST'])
@login_required
def compose_start():
    data = request.get_json()
    session_id = str(uuid.uuid4())
    progress_store[session_id] = 0
    thread = threading.Thread(target=background_task, args=(data, session_id))
    thread.start()
    return jsonify({"session_id": session_id})

@app.route('/compose/progress/<session_id>')
def compose_progress(session_id):
    progress = progress_store.get(session_id, 0)
    return jsonify({"progress": progress})

@app.route('/preview')
@login_required
def preview():
    return render_template('analysis-preview.html')

@app.route('/execution')
@login_required
def execution():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect(url_for('index'))
    video_filename = f"workout_{session_id}.mp4"
    video_url = url_for('static', filename=f'videos/{video_filename}')
    video_physical_path = os.path.join(VIDEO_FOLDER, video_filename)
    if not os.path.exists(video_physical_path):
        return f"影片尚未產生 (ID: {session_id}) <a href='/'>返回</a>"
    return render_template("exercise-execution.html", video_url=video_url, video_filename=video_filename)

@app.route('/results')
@login_required 
def exercise_results():
    return render_template('exercise-results.html')

@app.route('/personal')
@login_required 
def personal_data():
    return render_template('personal-data.html')

def background_task(data, session_id):
    clips = []
    audio_clips = []
    final_clip = None
    final_audio = None
    temp_files = []
    TARGET_SIZE = (640, 360)
    w, h = TARGET_SIZE

    try:
        actionTime = 20
        restTime = 10
        actions = data.get("actions_data", [])
        music_list = data.get("music_list", [])
        user_duration_min = float(data.get("duration", 5))
        total_target_duration = user_duration_min * 60 
        current_video_duration = 0
        
        while current_video_duration < total_target_duration:
            for i, action in enumerate(actions):
                if current_video_duration >= total_target_duration: break
                name = action.get("name", "運動")
                gif_url = action.get("gif_url")
                is_gif_success = False
                if gif_url:
                    try:
                        temp_gif_path = f"temp_{session_id}_{len(clips)}.gif"
                        if not os.path.exists(temp_gif_path):
                            response = requests.get(gif_url, stream=True, timeout=10)
                            if response.status_code == 200:
                                with open(temp_gif_path, 'wb') as f:
                                    shutil.copyfileobj(response.raw, f)
                                temp_files.append(temp_gif_path)
                        if os.path.exists(temp_gif_path):
                            gif_clip = VideoFileClip(temp_gif_path)
                            gif_resized = gif_clip.resize(height=h)
                            if gif_resized.w > w: gif_resized = gif_clip.resize(width=w)
                            background = ColorClip(size=TARGET_SIZE, color=(0,0,0), duration=actionTime)
                            looped_gif = gif_resized.fx(vfx.loop, duration=actionTime).set_position(('center', 'center'))
                            final_action_clip = CompositeVideoClip([background, looped_gif], size=TARGET_SIZE)
                            clips.append(final_action_clip)
                            is_gif_success = True
                    except: pass
                
                if not is_gif_success:
                    fallback = ColorClip(size=TARGET_SIZE, color=(0,0,0), duration=actionTime)
                    clips.append(fallback)

                current_video_duration += actionTime
                progress_store[session_id] = min(int((current_video_duration / total_target_duration) * 50), 50)

                if current_video_duration < total_target_duration:
                    rest_clip = ColorClip(size=TARGET_SIZE, color=(100,100,100), duration=restTime)
                    clips.append(rest_clip)
                    current_video_duration += restTime

        if not clips: clips.append(ColorClip(size=TARGET_SIZE, color=(0,0,0), duration=10))
        final_clip = concatenate_videoclips(clips)
        if final_clip.duration > total_target_duration:
            final_clip = final_clip.subclip(0, total_target_duration)

        if music_list:
            current_audio_time = 0
            idx = 0
            while current_audio_time < final_clip.duration:
                song = music_list[idx % len(music_list)]
                path = os.path.join(UPLOAD_FOLDER, song['name'])
                if not os.path.exists(path):
                    idx += 1; continue
                try:
                    audio = AudioFileClip(path)
                    if current_audio_time + audio.duration > final_clip.duration:
                        remain = final_clip.duration - current_audio_time
                        if remain > 0: audio = audio.subclip(0, remain)
                        else: break 
                    audio = audio.set_start(current_audio_time)
                    audio_clips.append(audio)
                    current_audio_time += audio.duration
                    idx += 1
                    prog = 50 + int((current_audio_time / final_clip.duration) * 50)
                    progress_store[session_id] = min(prog, 99)
                except: idx += 1
            if audio_clips:
                try:
                    final_audio = CompositeAudioClip(audio_clips)
                    final_clip = final_clip.set_audio(final_audio)
                except: pass

        output_path = os.path.join(VIDEO_FOLDER, f"workout_{session_id}.mp4")
        final_clip.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, logger=None)
        progress_store[session_id] = 100

    except Exception as e:
        print(f"!!! 背景任務崩潰: {e} !!!")
        progress_store[session_id] = -1 
        
    finally:
        try:
            if final_clip: final_clip.close()
            if final_audio: final_audio.close()
            for c in clips: c.close()
            for c in audio_clips: c.close()
        except: pass
        for f in temp_files:
            try: os.remove(f)
            except: pass

if __name__ == '__main__':
    app.run(debug=True)