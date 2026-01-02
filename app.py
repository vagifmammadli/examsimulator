import os
import re
import random
from flask import Flask, render_template_string, jsonify
import PyPDF2

app = Flask(__name__)

# PDF Faylının adı
PDF_FILENAME = 'mmsillabussu.pdf'

def extract_text_from_pdf(filename):
    """PDF-dən mətni çıxarır."""
    text = ""
    try:
        with open(filename, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF oxuma xətası: {e}")
        return None
    return text

def parse_quiz_content(text):
    """
    GÜCLƏNDİRİLMİŞ ANALİZ V3:
    1. '1 .', '1)', '1-' və ya sadəcə '1.' formatlarını dəstəkləyir.
    2. Variantların qarşısındakı '•' və '√' simvollarını təmizləyir.
    3. Sualı tapmaq üçün daha çevik məntiq işlədir.
    """
    questions = []
    lines = text.split('\n')
    
    current_question = None
    
    # YENİ REGEX (Çox daha geniş axtarış):
    # ^\s* -> Sətrin əvvəlində boşluq ola bilər
    # (\d+) -> Rəqəmi tut
    # \s* -> Rəqəmdən sonra boşluq ola bilər (Məs: "1 .")
    # [\.\)\-] -> Nöqtə, mötərizə və ya tire
    # \s* -> Sonra yenə boşluq
    # (.*) -> Mətn
    question_start_regex = re.compile(r'^\s*(\d+)\s*[\.\)\-]\s*(.*)')
    
    # Düzgün cavab işarələri (Şəkildə görünən √ daxildir)
    correct_markers = ['✔', '√', '+', '✓'] 
    
    # Variant başlanğıc simvolları (Təmizləmək üçün)
    bullet_markers = ['•', '●', '-', '*', ')']

    for line in lines:
        line = line.strip()
        
        # Boş və ya lazımsız sətirləri keç
        if not line or '--- PAGE' in line or 'Fənn:' in line:
            continue

        q_match = question_start_regex.match(line)

        # --- YENİ SUAL TAPILDI ---
        if q_match:
            # Köhnə sualı yaddaşa at
            if current_question:
                # Variant sayı az olsa belə, əgər sual mətni varsa əlavə et (bəzən parser variantları birləşdirir)
                if len(current_question['options']) > 0:
                    questions.append(current_question)
            
            # Yeni sual obyektini yarat
            current_question = {
                'id': int(q_match.group(1)),
                'text': q_match.group(2).strip(),
                'options': []
            }

        # --- SUALIN İÇİNDƏYİK ---
        elif current_question:
            # Sətirdə düzgün cavab işarəsi varmı?
            is_correct = any(marker in line for marker in correct_markers)
            
            # Sətir variant oxşayır? (İşarə ilə başlayırsa və ya qısa simvolla)
            # Şəkildəki '•' simvolunu xüsusi yoxlayırıq
            is_option_line = is_correct or any(line.startswith(b) for b in bullet_markers)
            
            # Əgər hələ heç bir variant yoxdursa və sətir variant kimi görünmürsə -> SUALIN DAVAMIDIR
            if not current_question['options'] and not is_option_line:
                 # Sadəcə böyük hərflə başlayan, amma variant olmayan cümlələri suala qatırıq
                 current_question['text'] += " " + line
            
            # Əks halda -> VARİANTDIR
            else:
                # 1. Variantın əvvəlki cümlənin davamı olub-olmadığını yoxla
                # Şərt: Yeni işarə yoxdur VƏ (kiçik hərflə başlayır VƏ YA vergüllə başlayır)
                is_continuation = not is_option_line and (len(line) > 0 and (line[0].islower() or line[0] in [',', ';', ':']))

                if is_continuation and current_question['options']:
                    current_question['options'][-1]['text'] += " " + line
                else:
                    # Yeni Variant əlavə et
                    option_text = line
                    
                    # Düzgün cavab işarəsini təmizlə
                    for marker in correct_markers:
                        option_text = option_text.replace(marker, '')
                    
                    # Bullet (•) və digər zibilləri təmizlə
                    # Bu regex sətrin əvvəlindəki bütün qeyri-hərf simvollarını silir
                    option_text = re.sub(r'^[\s•\-\*\)\.]+', '', option_text).strip()
                    
                    # Yalnız boş olmayan variantları götür
                    if option_text and not re.match(r'^\d+\.$', option_text):
                        current_question['options'].append({
                            'text': option_text,
                            'isCorrect': is_correct
                        })

    # Dövr bitəndə sonuncu sualı əlavə etməyi unutma
    if current_question and len(current_question['options']) > 0:
        questions.append(current_question)
        
    return questions

# --- HTML TEMPLATE (Eyni qalır) ---
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
    <header class="bg-blue-900 text-white shadow-md z-10">
        <div class="container mx-auto px-4 py-3 flex justify-between items-center">
            <div class="flex items-center space-x-3">
                <i class="fas fa-shield-alt text-2xl"></i>
                <h1 class="text-xl font-bold hidden md:block">Mülki Müdafiə İmtahanı</h1>
                <h1 class="text-xl font-bold md:hidden">MM İmtahan</h1>
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
                         <span id="qIdBadge" class="bg-gray-100 px-2 py-0.5 rounded text-xs">ID: #0</span>
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

            <div id="resultsScreen" class="hidden max-w-4xl mx-auto">
                <div class="bg-white rounded-xl shadow-lg p-8 mb-8 text-center border-t-4 border-blue-600">
                    <h2 class="text-3xl font-bold text-gray-800 mb-2">İmtahan Nəticəsi</h2>
                    <div class="text-6xl font-bold text-blue-600 my-6"><span id="finalScore">0</span><span class="text-2xl text-gray-400">/50</span></div>
                    <div class="grid grid-cols-3 gap-4 max-w-lg mx-auto mb-8">
                        <div class="p-3 bg-green-50 rounded border border-green-200"><div class="text-xl font-bold text-green-600" id="correctCount">0</div><div class="text-xs text-green-800 uppercase font-semibold">Düzgün</div></div>
                        <div class="p-3 bg-red-50 rounded border border-red-200"><div class="text-xl font-bold text-red-600" id="wrongCount">0</div><div class="text-xs text-red-800 uppercase font-semibold">Yanlış</div></div>
                        <div class="p-3 bg-gray-50 rounded border border-gray-200"><div class="text-xl font-bold text-gray-600" id="emptyCount">0</div><div class="text-xs text-gray-800 uppercase font-semibold">Boş</div></div>
                    </div>
                    <button onclick="location.reload()" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-bold shadow hover:bg-blue-700 transition">Yenidən Başla</button>
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

        async function loadQuestions() {
            try {
                const response = await fetch('/api/questions');
                const data = await response.json();
                
                if(data.error) {
                    // Xəta olduqda daha ətraflı məlumat göstər
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
                card.innerHTML = `<div class="flex gap-3"><div class="font-bold text-gray-500">${i+1}.</div><div class="flex-1"><p class="font-medium mb-2">${q.text}</p><div class="text-sm space-y-1">${status !== 'empty' ? `<div class="${status === 'correct' ? 'text-green-700 font-bold' : 'text-red-700 font-bold'}">Sizin cavab: ${q.options[userAnsIdx].text}</div>` : `<div class="text-gray-500 italic">Cavab verilməyib</div>`}<div class="text-green-700 bg-green-100 inline-block px-2 py-1 rounded text-xs font-bold mt-1">Doğru: ${correctOpt ? correctOpt.text : 'Təyin olunmayıb'}</div></div></div><div class="text-xl">${status === 'correct' ? '<i class="fas fa-check text-green-500"></i>' : status === 'wrong' ? '<i class="fas fa-times text-red-500"></i>' : '<i class="fas fa-minus text-gray-400"></i>'}</div></div>`;
                reviewContainer.appendChild(card);
            });
            document.getElementById('finalScore').innerText = correct; document.getElementById('correctCount').innerText = correct; document.getElementById('wrongCount').innerText = wrong; document.getElementById('emptyCount').innerText = empty;
            document.getElementById('quizContent').classList.add('hidden'); document.getElementById('resultsScreen').classList.remove('hidden'); document.querySelector('aside').classList.add('hidden');
        }
        function toggleMobileMap() { document.getElementById('mobileMapModal').classList.toggle('hidden'); }
        window.onload = loadQuestions;
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/questions')
def get_questions():
    if not os.path.exists(PDF_FILENAME):
        return jsonify({'error': f"'{PDF_FILENAME}' faylı tapılmadı."})
    
    text = extract_text_from_pdf(PDF_FILENAME)
    if not text:
        return jsonify({'error': "PDF-dən mətn oxuna bilmədi. Fayl zədəli və ya şəkil (scan) formatındadır."})

    all_questions = parse_quiz_content(text)
    
    if not all_questions:
        # Debug üçün ilk 500 simvolu göndər ki, problemi görək
        debug_snippet = text[:500] if text else "Mətn boşdur"
        return jsonify({
            'error': "Suallar tapılmadı. Zəhmət olmasa PDF formatını yoxlayın.",
            'debug': f"PDF-dən oxunan ilk hissə belə görünür:\n\n{debug_snippet}..."
        })

    count = min(len(all_questions), 50)
    selected_questions = random.sample(all_questions, count)
    
    for q in selected_questions:
        q['original_id'] = q['id']
        random.shuffle(q['options'])
        
    return jsonify(selected_questions)

if __name__ == '__main__':
    app.run(debug=True)