import os
import re
import random
import sqlite3
import uuid
from flask import Flask, render_template_string, jsonify, request, make_response
import PyPDF2

app = Flask(__name__)

# --- KONFİQURASİYA ---
PDF_FILENAME = 'mmsillabussu.pdf'
DB_FILENAME = 'quiz.db'

# --- VERİLƏNLƏR BAZASI ---
def init_db():
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    # username sütunu artıq UNIQUE (unikal) olacaq
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (machine_id TEXT PRIMARY KEY, username TEXT UNIQUE, score INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# --- PDF PARSER (Dəyişməyib) ---
def extract_text_from_pdf(filename):
    text = ""
    try:
        with open(filename, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text: text += page_text + "\n"
    except Exception as e: return None
    return text

def parse_quiz_content(text):
    questions = []
    lines = text.split('\n')
    current_question = None
    question_start_regex = re.compile(r'^\s*(\d+)\s*[\.\)\-]\s*(.*)')
    correct_markers = ['✔', '√', '+', '✓'] 
    bullet_markers = ['•', '●', '-', '*', ')']

    for line in lines:
        line = line.strip()
        if not line or '--- PAGE' in line or 'Fənn:' in line: continue
        q_match = question_start_regex.match(line)
        if q_match:
            if current_question and len(current_question['options']) > 0:
                questions.append(current_question)
            current_question = {'id': int(q_match.group(1)), 'text': q_match.group(2).strip(), 'options': []}
        elif current_question:
            is_correct = any(marker in line for marker in correct_markers)
            is_option_line = is_correct or any(line.startswith(b) for b in bullet_markers)
            if not current_question['options'] and not is_option_line:
                 current_question['text'] += " " + line
            else:
                is_continuation = not is_option_line and (len(line) > 0 and (line[0].islower() or line[0] in [',', ';', ':']))
                if is_continuation and current_question['options']:
                    current_question['options'][-1]['text'] += " " + line
                else:
                    option_text = line
                    for marker in correct_markers: option_text = option_text.replace(marker, '')
                    option_text = re.sub(r'^[\s•\-\*\)\.]+', '', option_text).strip()
                    if option_text and not re.match(r'^\d+\.$', option_text):
                        current_question['options'].append({'text': option_text, 'isCorrect': is_correct})
    if current_question and len(current_question['options']) > 0:
        questions.append(current_question)
    return questions

# --- HTML ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="az">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mülki Müdafiə - İmtahan</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; user-select: none; }
        .option-input:checked + .option-label { background-color: #e0f2fe; border-color: #3b82f6; color: #1e40af; }
        .map-btn.current { border: 2px solid #f59e0b; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-thumb { background: #888; border-radius: 4px; }
    </style>
</head>
<body class="flex flex-col h-screen overflow-hidden">

    <div id="loginModal" class="fixed inset-0 bg-black bg-opacity-90 z-50 flex items-center justify-center {{ 'hidden' if user_exists else '' }}">
        <div class="bg-white p-8 rounded-xl shadow-2xl max-w-md w-full text-center">
            <i class="fas fa-user-shield text-5xl text-blue-900 mb-4"></i>
            <h2 class="text-2xl font-bold text-gray-800 mb-2">Xoş Gəlmisiniz!</h2>
            <p class="text-gray-600 mb-6">İmtahana başlamaq üçün adınızı daxil edin.</p>
            
            <input type="text" id="usernameInput" class="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:ring-2 focus:ring-blue-500 outline-none" placeholder="Ad Soyad (Unikal olmalıdır)">
            
            <div id="loginError" class="text-red-600 text-sm font-bold mb-3 hidden"></div>
            
            <button onclick="registerUser()" class="w-full bg-blue-600 text-white py-3 rounded-lg font-bold hover:bg-blue-700 transition">Başla</button>
        </div>
    </div>

    <header class="bg-blue-900 text-white shadow-md z-10">
        <div class="container mx-auto px-4 py-3 flex justify-between items-center">
            <div class="flex items-center space-x-3">
                <i class="fas fa-shield-alt text-2xl"></i>
                <div class="leading-tight">
                    <h1 class="text-xl font-bold">Mülki Müdafiə</h1>
                    <div class="text-xs text-blue-200" id="headerUsername">{{ username if username else 'Qonaq' }}</div>
                </div>
            </div>
            <div class="flex items-center space-x-4">
                <div class="text-sm font-medium bg-blue-800 px-3 py-1 rounded-full border border-blue-700">
                    <i class="far fa-clock mr-1"></i> <span id="timer">00:00</span>
                </div>
                <button onclick="finishQuiz()" class="bg-red-600 hover:bg-red-700 text-white px-4 py-1.5 rounded text-sm font-bold transition shadow">Bitir</button>
            </div>
        </div>
    </header>

    <div id="errorModal" class="fixed inset-0 bg-black bg-opacity-75 z-50 flex items-center justify-center hidden">
        <div class="bg-white p-8 rounded-lg text-center max-w-md">
            <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
            <h2 class="text-xl font-bold mb-2">Xəta</h2>
            <p id="errorMessage" class="text-gray-600 mb-4"></p>
            <div id="debugInfo" class="text-xs text-left bg-gray-100 p-2 rounded mb-4 max-h-32 overflow-auto hidden"></div>
            <button onclick="location.reload()" class="bg-blue-600 text-white px-4 py-2 rounded">Yenidən cəhd et</button>
        </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
        <aside class="w-full md:w-80 bg-white border-r border-gray-200 flex flex-col hidden md:flex z-20">
            <div class="p-4 border-b border-gray-200 bg-gray-50">
                <h2 class="font-bold text-gray-700">Sual Paneli</h2>
                <div class="flex items-center justify-between text-xs text-gray-500 mt-2">
                    <span class="flex items-center"><div class="w-3 h-3 bg-blue-600 rounded-sm mr-1"></div> Yazılıb</span>
                    <span class="flex items-center"><div class="w-3 h-3 bg-white border border-gray-300 rounded-sm mr-1"></div> Boş</span>
                    <span class="flex items-center"><div class="w-3 h-3 border-2 border-yellow-500 rounded-sm mr-1"></div> Cari</span>
                </div>
            </div>
            <div class="flex-1 overflow-y-auto p-4">
                <div id="questionMap" class="grid grid-cols-5 gap-2"></div>
            </div>
        </aside>

        <main class="flex-1 overflow-y-auto p-4 md:p-8 relative" id="mainContainer">
            <div id="loadingIndicator" class="absolute inset-0 flex items-center justify-center bg-gray-100 z-40">
                <div class="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600"></div>
            </div>

            <div id="quizContent" class="max-w-4xl mx-auto hidden">
                <div class="bg-white rounded-xl shadow-lg p-6 md:p-8 mb-6">
                    <div class="flex justify-between items-center mb-4 text-gray-500 text-sm">
                         <span>Sual <span id="currentQNum">1</span> / <span id="totalQNum">50</span></span>
                         <span id="qIdBadge" class="bg-gray-100 px-2 py-0.5 rounded text-xs font-mono font-bold text-gray-600">ID: #0</span>
                    </div>
                    <h2 id="questionText" class="text-xl md:text-2xl font-semibold text-gray-800 mb-6 leading-relaxed"></h2>
                    <div id="optionsContainer" class="space-y-3"></div>
                </div>
                <div class="flex justify-between items-center">
                    <button id="prevBtn" onclick="changeQuestion(-1)" class="px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 shadow-sm transition disabled:opacity-50"><i class="fas fa-chevron-left mr-2"></i> Əvvəlki</button>
                    <button id="toggleMapMobile" onclick="toggleMobileMap()" class="md:hidden px-4 py-3 bg-blue-100 text-blue-800 rounded-lg"><i class="fas fa-th-large"></i></button>
                    <button id="nextBtn" onclick="changeQuestion(1)" class="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-md transition">Növbəti <i class="fas fa-chevron-right ml-2"></i></button>
                </div>
            </div>

            <div id="resultsScreen" class="hidden max-w-4xl mx-auto space-y-8">
                <div class="bg-white rounded-xl shadow-lg p-8 text-center border-t-4 border-blue-600">
                    <h2 class="text-3xl font-bold text-gray-800 mb-2">İmtahan Nəticəsi</h2>
                    <div class="text-6xl font-bold text-blue-600 my-6"><span id="finalScore">0</span><span class="text-2xl text-gray-400">/50</span></div>
                    <div class="grid grid-cols-3 gap-4 max-w-lg mx-auto mb-8">
                        <div class="p-3 bg-green-50 rounded border border-green-200"><div class="text-xl font-bold text-green-600" id="correctCount">0</div><div class="text-xs text-green-800 uppercase font-semibold">Düzgün</div></div>
                        <div class="p-3 bg-red-50 rounded border border-red-200"><div class="text-xl font-bold text-red-600" id="wrongCount">0</div><div class="text-xs text-red-800 uppercase font-semibold">Yanlış</div></div>
                        <div class="p-3 bg-gray-50 rounded border border-gray-200"><div class="text-xl font-bold text-gray-600" id="emptyCount">0</div><div class="text-xs text-gray-800 uppercase font-semibold">Boş</div></div>
                    </div>
                    <button onclick="location.reload()" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-bold shadow hover:bg-blue-700 transition">Yenidən Başla</button>
                </div>

                <div class="bg-white rounded-xl shadow-lg p-8 border-t-4 border-yellow-500">
                    <h3 class="text-2xl font-bold text-gray-800 mb-4 flex items-center"><i class="fas fa-trophy text-yellow-500 mr-2"></i> Liderlər Lövhəsi (Top 10)</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left">
                            <thead class="bg-gray-100 text-gray-600 uppercase text-xs">
                                <tr>
                                    <th class="px-4 py-3">Rank</th>
                                    <th class="px-4 py-3">İstifadəçi</th>
                                    <th class="px-4 py-3 text-right">Ən Yüksək Bal</th>
                                </tr>
                            </thead>
                            <tbody id="leaderboardTable" class="text-sm"><tr><td colspan="3" class="px-4 py-3 text-center text-gray-500">Yüklənir...</td></tr></tbody>
                        </table>
                    </div>
                </div>
                <div class="bg-white rounded-xl shadow-lg p-8"><h3 class="text-xl font-bold text-gray-800 mb-6">Ətraflı Analiz</h3><div id="reviewContainer" class="space-y-6"></div></div>
            </div>
        </main>
    </div>

    <div id="mobileMapModal" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden md:hidden" onclick="toggleMobileMap()">
        <div class="absolute bottom-0 left-0 right-0 bg-white rounded-t-xl p-4 max-h-[70vh] overflow-y-auto" onclick="event.stopPropagation()"><div class="grid grid-cols-5 gap-3" id="mobileQuestionMap"></div></div>
    </div>

    <script>
        let questions = [];
        let userAnswers = {};
        let currentQuestionIndex = 0;
        let startTime;
        let timerInterval;

        async function registerUser() {
            const usernameInput = document.getElementById('usernameInput');
            const errorDiv = document.getElementById('loginError');
            const username = usernameInput.value.trim();
            
            errorDiv.classList.add('hidden');
            if(!username) { 
                errorDiv.innerText = "Zəhmət olmasa adınızı daxil edin.";
                errorDiv.classList.remove('hidden');
                return; 
            }

            try {
                const res = await fetch('/api/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: username})
                });
                const data = await res.json();
                
                if(data.success) {
                    location.reload(); 
                } else {
                    // Xəta mesajını göstər (Məs: Ad tutulub)
                    errorDiv.innerText = data.error || "Xəta baş verdi.";
                    errorDiv.classList.remove('hidden');
                }
            } catch (e) {
                errorDiv.innerText = "Serverlə əlaqə xətası.";
                errorDiv.classList.remove('hidden');
            }
        }

        async function loadQuestions() {
            if(!document.getElementById('loginModal').classList.contains('hidden')) return;

            try {
                const response = await fetch('/api/questions');
                const data = await response.json();
                
                if(data.error) {
                    document.getElementById('debugInfo').innerText = data.debug || "";
                    document.getElementById('debugInfo').classList.remove('hidden');
                    throw new Error(data.error);
                }
                
                questions = data;
                userAnswers = new Array(questions.length).fill(null);
                document.getElementById('loadingIndicator').classList.add('hidden');
                document.getElementById('quizContent').classList.remove('hidden');
                document.getElementById('totalQNum').innerText = questions.length;
                renderMap();
                renderQuestion(0);
                startTimer();
            } catch (error) {
                document.getElementById('loadingIndicator').classList.add('hidden');
                document.getElementById('errorModal').classList.remove('hidden');
                document.getElementById('errorMessage').innerText = error.message;
            }
        }

        async function loadLeaderboard() {
            const res = await fetch('/api/leaderboard');
            const users = await res.json();
            const tbody = document.getElementById('leaderboardTable');
            tbody.innerHTML = '';
            
            users.forEach((user, index) => {
                let rankIcon = '';
                if(index === 0) rankIcon = '🥇';
                else if(index === 1) rankIcon = '🥈';
                else if(index === 2) rankIcon = '🥉';
                else rankIcon = `#${index + 1}`;

                const tr = document.createElement('tr');
                tr.className = "border-b border-gray-100 hover:bg-gray-50";
                tr.innerHTML = `<td class="px-4 py-3 font-bold text-blue-900">${rankIcon}</td><td class="px-4 py-3 font-medium text-gray-700">${user.username}</td><td class="px-4 py-3 text-right font-bold text-gray-800">${user.score}</td>`;
                tbody.appendChild(tr);
            });
        }

        async function submitScore(score) {
            await fetch('/api/submit_score', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({score: score})
            });
            loadLeaderboard();
        }

        function renderQuestion(index) {
            const q = questions[index];
            currentQuestionIndex = index;
            document.getElementById('currentQNum').innerText = index + 1;
            document.getElementById('qIdBadge').innerText = `ID: #${q.original_id}`;
            document.getElementById('questionText').innerText = q.text;
            const container = document.getElementById('optionsContainer');
            container.innerHTML = '';
            q.options.forEach((opt, idx) => {
                const isChecked = userAnswers[index] === idx;
                const div = document.createElement('div');
                div.innerHTML = `
                    <input type="radio" name="q_${index}" id="opt_${idx}" class="option-input hidden peer" ${isChecked ? 'checked' : ''} onchange="selectOption(${index}, ${idx})">
                    <label for="opt_${idx}" class="option-label block w-full p-4 bg-gray-50 border-2 border-transparent rounded-lg hover:bg-gray-100 peer-checked:bg-blue-50 peer-checked:border-blue-500 peer-checked:text-blue-700 cursor-pointer transition-all">
                        <div class="flex items-center">
                            <div class="w-6 h-6 border-2 border-gray-300 rounded-full flex items-center justify-center mr-3 peer-checked:bg-blue-500 peer-checked:border-blue-500"><div class="w-2.5 h-2.5 bg-white rounded-full ${isChecked ? '' : 'hidden'}"></div></div>
                            <span>${opt.text}</span>
                        </div>
                    </label>`;
                container.appendChild(div);
            });
            document.getElementById('prevBtn').disabled = index === 0;
            const nextBtn = document.getElementById('nextBtn');
            if (index === questions.length - 1) {
                nextBtn.innerHTML = 'Bitir <i class="fas fa-check-circle ml-2"></i>';
                nextBtn.className = "px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 shadow-md transition";
                nextBtn.onclick = finishQuiz;
            } else {
                nextBtn.innerHTML = 'Növbəti <i class="fas fa-chevron-right ml-2"></i>';
                nextBtn.className = "px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-md transition";
                nextBtn.onclick = () => changeQuestion(1);
            }
            updateMapHighlights();
        }

        function selectOption(qIndex, optIndex) { userAnswers[qIndex] = optIndex; updateMapHighlights(); }
        function changeQuestion(delta) { const newIndex = currentQuestionIndex + delta; if (newIndex >= 0 && newIndex < questions.length) renderQuestion(newIndex); }
        function renderMap() { document.getElementById('questionMap').innerHTML = questions.map((_, i) => `<button id="mapBtn_${i}" onclick="renderQuestion(${i})" class="map-btn w-full aspect-square flex items-center justify-center border rounded text-sm font-medium hover:bg-gray-100 transition">${i + 1}</button>`).join(''); document.getElementById('mobileQuestionMap').innerHTML = document.getElementById('questionMap').innerHTML; }
        function updateMapHighlights() { questions.forEach((_, i) => { const btn = document.getElementById(`mapBtn_${i}`); const mobBtn = document.getElementById(`mobileQuestionMap`).children[i]; let cls = "map-btn w-full aspect-square flex items-center justify-center border rounded text-sm font-medium transition "; if (i === currentQuestionIndex) cls += "border-yellow-500 ring-2 ring-yellow-200 z-10 "; else cls += "border-gray-200 "; if (userAnswers[i] !== null) cls += "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"; else cls += "bg-white text-gray-700 hover:bg-gray-50"; btn.className = cls; if(mobBtn) mobBtn.className = cls; }); }
        function startTimer() { startTime = Date.now(); timerInterval = setInterval(() => { const diff = Math.floor((Date.now() - startTime) / 1000); document.getElementById('timer').innerText = `${Math.floor(diff / 60).toString().padStart(2, '0')}:${(diff % 60).toString().padStart(2, '0')}`; }, 1000); }
        
        function finishQuiz() {
            if(!confirm("İmtahanı tamamlamaq istədiyinizə əminsiniz?")) return;
            clearInterval(timerInterval);
            let correct = 0, wrong = 0, empty = 0;
            const reviewContainer = document.getElementById('reviewContainer');
            reviewContainer.innerHTML = '';
            questions.forEach((q, i) => {
                const userAnsIdx = userAnswers[i];
                const correctOpt = q.options.find(o => o.isCorrect);
                let status = 'empty';
                if(userAnsIdx !== null) { if(q.options[userAnsIdx].isCorrect) { correct++; status = 'correct'; } else { wrong++; status = 'wrong'; } } else { empty++; }
                
                const card = document.createElement('div');
                card.className = `p-4 border rounded-lg ${status === 'correct' ? 'bg-green-50 border-green-200' : status === 'wrong' ? 'bg-red-50 border-red-200' : 'bg-gray-50'}`;
                card.innerHTML = `<div class="flex gap-3"><div class="flex flex-col items-center justify-start min-w-[3rem]"><span class="font-bold text-gray-600 text-xl">${i+1}.</span><span class="text-[10px] text-gray-500 bg-gray-200 px-1.5 rounded mt-1 font-mono">ID:${q.original_id}</span></div><div class="flex-1"><p class="font-medium mb-2">${q.text}</p><div class="text-sm space-y-1">${status !== 'empty' ? `<div class="${status === 'correct' ? 'text-green-700 font-bold' : 'text-red-700 font-bold'}">Sizin cavab: ${q.options[userAnsIdx].text}</div>` : `<div class="text-gray-500 italic">Cavab verilməyib</div>`}<div class="text-green-700 bg-green-100 inline-block px-2 py-1 rounded text-xs font-bold mt-1">Doğru: ${correctOpt ? correctOpt.text : 'Təyin olunmayıb'}</div></div></div><div class="text-xl">${status === 'correct' ? '<i class="fas fa-check text-green-500"></i>' : status === 'wrong' ? '<i class="fas fa-times text-red-500"></i>' : '<i class="fas fa-minus text-gray-400"></i>'}</div></div>`;
                reviewContainer.appendChild(card);
            });
            document.getElementById('finalScore').innerText = correct; document.getElementById('correctCount').innerText = correct; document.getElementById('wrongCount').innerText = wrong; document.getElementById('emptyCount').innerText = empty;
            submitScore(correct);
            document.getElementById('quizContent').classList.add('hidden'); document.getElementById('resultsScreen').classList.remove('hidden'); document.querySelector('aside').classList.add('hidden');
        }
        
        function toggleMobileMap() { document.getElementById('mobileMapModal').classList.toggle('hidden'); }
        window.onload = loadQuestions;
    </script>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/')
def index():
    machine_id = request.cookies.get('quiz_user_id')
    user_exists = False
    username = None

    if machine_id:
        conn = sqlite3.connect(DB_FILENAME)
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE machine_id=?", (machine_id,))
        result = c.fetchone()
        conn.close()
        
        # DÜZƏLİŞ: Əgər cookie var, amma baza boşdursa (user silinib),
        # 'user_exists = False' qoyuruq ki, yenidən qeydiyyat pəncərəsi açılsın.
        if result:
            user_exists = True
            username = result[0]
        else:
            # Cookie var, amma user yoxdur (Zombie Cookie).
            user_exists = False

    return render_template_string(HTML_TEMPLATE, user_exists=user_exists, username=username)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    
    # DÜZƏLİŞ: İlk öncə ADIN tutulub-tutulmadığını yoxlayırıq
    c.execute("SELECT machine_id FROM users WHERE username=?", (username,))
    existing_user = c.fetchone()
    
    if existing_user:
        conn.close()
        return jsonify({'success': False, 'error': 'Bu ad artıq istifadə olunur. Zəhmət olmasa başqa ad seçin.'})

    # DÜZƏLİŞ: Əgər köhnə cookie varsa da, onu yeniləyəcəyik (Loop probleminin həlli)
    # Yeni unikal ID yaradılır
    new_machine_id = str(uuid.uuid4())
    
    try:
        c.execute("INSERT INTO users (machine_id, username, score) VALUES (?, ?, 0)", (new_machine_id, username))
        conn.commit()
        conn.close()
        
        resp = make_response(jsonify({'success': True}))
        # Cookie yenilənir
        resp.set_cookie('quiz_user_id', new_machine_id, max_age=60*60*24*365*10)
        return resp
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/submit_score', methods=['POST'])
def save_score():
    machine_id = request.cookies.get('quiz_user_id')
    if not machine_id: return jsonify({'error': 'No user'})
    
    new_score = request.json.get('score', 0)
    
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("SELECT score FROM users WHERE machine_id=?", (machine_id,))
    current = c.fetchone()
    
    if current and new_score > current[0]:
        c.execute("UPDATE users SET score=? WHERE machine_id=?", (new_score, machine_id))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/leaderboard')
def get_leaderboard():
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
    users = [{'username': row[0], 'score': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/questions')
def get_questions_api():
    if not os.path.exists(PDF_FILENAME):
        return jsonify({'error': f"'{PDF_FILENAME}' faylı tapılmadı."})
    
    text = extract_text_from_pdf(PDF_FILENAME)
    if not text:
        return jsonify({'error': "PDF-dən mətn oxuna bilmədi."})

    all_questions = parse_quiz_content(text)
    
    if not all_questions:
        debug_snippet = text[:500] if text else "Mətn boşdur"
        return jsonify({'error': "Suallar tapılmadı.", 'debug': f"PDF-dən oxunan ilk hissə:\n{debug_snippet}..."})

    count = min(len(all_questions), 50)
    selected_questions = random.sample(all_questions, count)
    for q in selected_questions:
        q['original_id'] = q['id']
        random.shuffle(q['options'])
        
    return jsonify(selected_questions)

if __name__ == '__main__':
    app.run(debug=True)