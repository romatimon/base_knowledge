import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import hashlib
from contextlib import contextmanager

# Настройка
ADMIN_PASSWORD = "admin123"  # Измени на свой пароль
DB_FILE = "knowledge.db"

# Контекстный менеджер для работы с БД
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
    finally:
        conn.close()

# Хэширование пароля для сравнения
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Хэш пароля по умолчанию (для admin123)
ADMIN_PASSWORD_HASH = hash_password(ADMIN_PASSWORD)

# Функция для форматирования времени
def format_datetime(timestamp):
    try:
        # Предполагаем, что время в UTC (как хранит SQLite)
        utc_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        # Добавляем 3 часа для московского времени
        moscow_dt = utc_dt + timedelta(hours=3)
        # Форматируем для вывода
        return moscow_dt.strftime('%d.%m.%Y %H:%M')
    except:
        return timestamp

st.set_page_config(
    page_title="База знаний",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инициализация состояния сессии
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False

# Создание базы данных
def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sections
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      title TEXT NOT NULL,
                      description TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS questions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      section_id INTEGER,
                      question TEXT NOT NULL,
                      answer TEXT,
                      info TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (section_id) REFERENCES sections (id))''')
        conn.commit()

init_db()

# Функции для работы с БД
@st.cache_data(ttl=300)  # Кэшируем на 5 минут
def get_sections():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM sections ORDER BY title", conn)

def get_questions(section_id):
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM questions WHERE section_id = ? ORDER BY id", 
                          conn, params=(section_id,))

def search_questions(search_text):
    with get_db_connection() as conn:
        query = """
        SELECT q.*, s.title as section_title 
        FROM questions q
        JOIN sections s ON q.section_id = s.id
        WHERE q.question LIKE ? 
           OR q.answer LIKE ?
           OR q.info LIKE ?
        ORDER BY s.title, q.id
        """
        search_param = f"%{search_text}%"
        return pd.read_sql(query, conn, params=(search_param, search_param, search_param))

@st.cache_data(ttl=300)
def get_recent_sections(limit=5):
    with get_db_connection() as conn:
        return pd.read_sql(f"SELECT * FROM sections ORDER BY created_at DESC LIMIT {limit}", conn)

@st.cache_data(ttl=300)
def get_recent_questions(limit=5):
    with get_db_connection() as conn:
        query = f"""
        SELECT q.*, s.title as section_title 
        FROM questions q
        JOIN sections s ON q.section_id = s.id
        ORDER BY q.created_at DESC 
        LIMIT {limit}
        """
        return pd.read_sql(query, conn)

def get_total_stats():
    with get_db_connection() as conn:
        sections_count = pd.read_sql("SELECT COUNT(*) as count FROM sections", conn).iloc[0]['count']
        questions_count = pd.read_sql("SELECT COUNT(*) as count FROM questions", conn).iloc[0]['count']
        return sections_count, questions_count

def add_section(title, description):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sections (title, description) VALUES (?, ?)", 
                  (title, description))
        conn.commit()

def add_question(section_id, question, answer, info):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO questions (section_id, question, answer, info) VALUES (?, ?, ?, ?)",
                  (section_id, question, answer, info))
        conn.commit()

def update_question(question_id, question, answer, info):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE questions SET question = ?, answer = ?, info = ? WHERE id = ?",
                  (question, answer, info, question_id))
        conn.commit()

def update_section(section_id, title, description):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE sections SET title = ?, description = ? WHERE id = ?",
                  (title, description, section_id))
        conn.commit()

def delete_section(section_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        c.execute("DELETE FROM questions WHERE section_id = ?", (section_id,))
        conn.commit()

def delete_question(question_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.commit()

# ===== БОКОВАЯ ПАНЕЛЬ =====
with st.sidebar:
    st.header("📚 База знаний")
    
    # Поиск - УПРОЩЕННАЯ ЛОГИКА
    search_container = st.container()
    
    with search_container:
        search_text = st.text_input(
            "🔍 Поиск", 
            placeholder="Введите запрос и нажмите Enter...",
            value=st.session_state.get("search_text", ""),
            key="search_input",
            label_visibility="collapsed"
        )
        
        col1, col2 = st.columns([3, 1])
        with col1:
            search_clicked = st.button("Найти", use_container_width=True, key="search_button")
        with col2:
            # Кнопка очистки поиска
            if st.session_state.get("search_mode"):
                if st.button("✖", use_container_width=True, key="clear_search"):
                    if "search_mode" in st.session_state:
                        del st.session_state["search_mode"]
                    if "search_text" in st.session_state:
                        del st.session_state["search_text"]
                    st.rerun()
    
    # Обработка поиска - срабатывает при нажатии кнопки ИЛИ при вводе текста и нажатии Enter
    if search_clicked or (search_text and search_text != st.session_state.get("last_search", "")):
        if search_text.strip():
            st.session_state["search_mode"] = True
            st.session_state["search_text"] = search_text
            st.session_state["last_search"] = search_text
            st.rerun()
        elif search_clicked:  # Только если нажата кнопка (не Enter)
            st.warning("Введите текст для поиска")
    
    st.write("---")
    
    # Панель админа
    if not st.session_state.admin_logged_in:
        with st.form("admin_login"):
            password = st.text_input("Пароль админа", type="password")
            if st.form_submit_button("Войти как админ"):
                if hash_password(password) == ADMIN_PASSWORD_HASH:
                    st.session_state.admin_logged_in = True
                    st.rerun()
                else:
                    st.error("Неверный пароль")
    else:
        st.success("✅ Админ")
        if st.button("Выйти", use_container_width=True):
            st.session_state.admin_logged_in = False
            st.rerun()
    
    st.write("---")
    st.subheader("📂 Разделы")
    
    # Кнопка "Главная"
    if st.button("🏠 Главная", use_container_width=True, key="main_button"):
        # Очищаем все состояния связанные с поиском и разделами
        for key in ["search_mode", "search_text", "current_section", "section_title"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
    
    # Получаем список разделов
    sections_df = get_sections()
    
    if not sections_df.empty:
        st.write("---")
        
        # Показываем разделы как кликабельные кнопки
        for _, section in sections_df.iterrows():
            if st.button(f"📁 {section['title']}", 
                        use_container_width=True,
                        key=f"nav_{section['id']}"):
                # Выходим из режима поиска
                if "search_mode" in st.session_state:
                    del st.session_state["search_mode"]
                if "search_text" in st.session_state:
                    del st.session_state["search_text"]
                st.session_state["current_section"] = section['id']
                st.session_state["section_title"] = section['title']
                st.rerun()
    else:
        st.info("Нет разделов")

# ===== ГЛАВНАЯ ОБЛАСТЬ =====
# Режим поиска
if st.session_state.get("search_mode"):
    search_text = st.session_state.get("search_text", "")
    
    if st.button("← Назад"):
        del st.session_state["search_mode"]
        if "search_text" in st.session_state:
            del st.session_state["search_text"]
        st.rerun()
    
    st.subheader(f"🔍 Результаты поиска: '{search_text}'")
    
    results = search_questions(search_text)
    
    if not results.empty:
        for _, question in results.iterrows():
            with st.expander(f"📁 {question['section_title']} » {question['question'][:50]}..."):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("**Вопрос / Ситуация**")
                    st.write(question['question'])
                
                with col2:
                    st.markdown("**Ответ / Действия**")
                    st.write(question['answer'] if question['answer'] else "—")
                
                with col3:
                    st.markdown("**Дополнительно**")
                    st.write(question['info'] if question['info'] else "—")
    else:
        st.info("Ничего не найдено")

# Режим просмотра раздела
elif "current_section" in st.session_state:
    section_id = st.session_state["current_section"]
    section_title = st.session_state.get("section_title", "")
    
    # Получаем информацию о разделе
    with get_db_connection() as conn:
        section_info = pd.read_sql(f"SELECT * FROM sections WHERE id = {section_id}", conn)
    
    if not section_info.empty:
        current_section = section_info.iloc[0]
        current_desc = current_section['description']
        
        # Кнопка назад
        if st.button("← Назад к разделам"):
            del st.session_state["current_section"]
            if "section_title" in st.session_state:
                del st.session_state["section_title"]
            st.rerun()
        
        # Заголовок раздела
        col_title, col_stats, col_admin = st.columns([3, 1, 1])
        with col_title:
            st.subheader(section_title)
            if current_desc:
                st.caption(current_desc)
        with col_stats:
            questions_df = get_questions(section_id)
            st.metric("Вопросов", len(questions_df))
        
        # Кнопки редактирования раздела для админа
        if st.session_state.admin_logged_in:
            with col_admin:
                if st.button("✏️ Редакт. раздел", use_container_width=True):
                    st.session_state["editing_section"] = section_id
        
        # Форма редактирования раздела
        if st.session_state.admin_logged_in and "editing_section" in st.session_state and st.session_state.editing_section == section_id:
            with st.form(f"edit_section_{section_id}"):
                new_title = st.text_input("Название раздела", value=section_title)
                new_desc = st.text_area("Описание раздела", value=current_desc if current_desc else "")
                
                col_save, col_cancel, col_delete = st.columns(3)
                with col_save:
                    if st.form_submit_button("💾 Сохранить", use_container_width=True):
                        update_section(section_id, new_title, new_desc)
                        st.session_state["section_title"] = new_title
                        del st.session_state["editing_section"]
                        st.success("Раздел обновлен!")
                        st.rerun()
                with col_cancel:
                    if st.form_submit_button("❌ Отмена", use_container_width=True):
                        del st.session_state["editing_section"]
                        st.rerun()
                with col_delete:
                    if st.form_submit_button("🗑️ Удалить", use_container_width=True):
                        delete_section(section_id)
                        del st.session_state["editing_section"]
                        del st.session_state["current_section"]
                        st.success("Раздел удален!")
                        st.rerun()
        
        # Форма добавления вопроса (только для админа)
        if st.session_state.admin_logged_in:
            with st.expander("➕ Добавить новый вопрос", expanded=False):
                with st.form(f"add_q_{section_id}", clear_on_submit=True):
                    question_text = st.text_area("Вопрос / Ситуация", height=100)
                    answer_text = st.text_area("Ответ / Порядок действий", height=150)
                    info_text = st.text_area("Дополнительно / Важно", height=100)
                    
                    if st.form_submit_button("Добавить"):
                        if question_text:
                            add_question(section_id, question_text, answer_text, info_text)
                            st.success("Вопрос добавлен!")
                            st.rerun()
        
        # Показываем вопросы
        questions_df = get_questions(section_id)
        
        if not questions_df.empty:
            for idx, question in questions_df.iterrows():
                with st.expander(f"❓ {question['question'][:80]}...", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("**Вопрос / Ситуация**")
                        st.info(question['question'])
                    
                    with col2:
                        st.markdown("**Ответ / Действия**")
                        if question['answer']:
                            st.success(question['answer'])
                        else:
                            st.write("—")
                    
                    with col3:
                        st.markdown("**Дополнительно**")
                        if question['info']:
                            st.warning(question['info'])
                        else:
                            st.write("—")
                    
                    # Кнопки управления для админа
                    if st.session_state.admin_logged_in:
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button(f"✏️ Редактировать", key=f"edit_{question['id']}", use_container_width=True):
                                st.session_state[f"editing_{question['id']}"] = True
                        with col_btn2:
                            if st.button(f"🗑️ Удалить", key=f"del_{question['id']}", use_container_width=True):
                                delete_question(question['id'])
                                st.success("Вопрос удален!")
                                st.rerun()
                        
                        # Форма редактирования вопроса
                        if f"editing_{question['id']}" in st.session_state:
                            with st.form(f"edit_form_{question['id']}"):
                                edit_q = st.text_area("Вопрос", value=question['question'], height=100)
                                edit_a = st.text_area("Ответ", value=question['answer'], height=150)
                                edit_i = st.text_area("Дополнительно", value=question['info'] if question['info'] else "", height=100)
                                
                                col_save, col_cancel = st.columns(2)
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", use_container_width=True):
                                        update_question(question['id'], edit_q, edit_a, edit_i)
                                        del st.session_state[f"editing_{question['id']}"]
                                        st.success("Изменения сохранены!")
                                        st.rerun()
                                with col_cancel:
                                    if st.form_submit_button("❌ Отмена", use_container_width=True):
                                        del st.session_state[f"editing_{question['id']}"]
                                        st.rerun()
        else:
            st.info("В этом разделе пока нет вопросов.")

# ===== ГЛАВНАЯ СТРАНИЦА =====
else:
    st.title("📚 База знаний для сотрудников")
    
    # Свертываемые инструкции
    with st.expander("📖 Инструкция по использованию", expanded=False):
        col_user, col_admin = st.columns(2)
        
        with col_user:
            st.subheader("👤 Для пользователей")
            st.markdown("""
            **🔍 Поиск информации:**
            1. Введите ключевые слова в поле поиска (боковая панель)
            2. Нажмите Enter или кнопку "Найти"
            
            **📂 Просмотр по разделам:**
            1. Выберите раздел в боковой панели
            2. Кликните на вопрос для просмотра
            3. Используйте кнопки "Назад" для возврата
            
            **🎯 Быстрый доступ:**
            - **🏠 Главная** - возврат на эту страницу
            - **📥 Недавние** - новые разделы и вопросы ниже
            """)
        
        if st.session_state.admin_logged_in:
            with col_admin:
                st.subheader("🔧 Для администратора")
                st.markdown("""
                **📁 Управление разделами:**
                - **Создать:** Форма "Создать новый раздел" ниже
                - **Редактировать:** Кнопка ✏️ в заголовке раздела
                - **Удалить:** Кнопка 🗑️ в форме редактирования
                
                **❓ Управление вопросами:**
                - **Добавить:** Кнопка ➕ в разделе
                - **Редактировать:** Кнопка ✏️ под вопросом
                - **Удалить:** Кнопка 🗑️ под вопросом
                
                **⚠️ Важно:**
                - Все изменения сохраняются сразу
                - Удаленные данные не восстанавливаются
                - Не забывайте выходить из аккаунта 🔐
                """)
        else:
            with col_admin:
                st.subheader("🔐 Для администраторов")
                st.info("""
                Войдите в систему для управления базой знаний:
                1. Введите пароль в боковой панели
                2. Нажмите "Войти как админ"
                3. Получите доступ к редактированию
                """)
    
    # Быстрая статистика
    sections_count, questions_count = get_total_stats()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📁 Всего разделов", sections_count)
    with col2:
        st.metric("❓ Всего вопросов", questions_count)
    
    st.write("---")
    
    # ВОССТАНАВЛИВАЕМ ПАНЕЛЬ УПРАВЛЕНИЯ РАЗДЕЛАМИ ДЛЯ АДМИНА
    if st.session_state.admin_logged_in:
        st.subheader("🛠️ Управление разделами (админ)")
        
        # Создание нового раздела
        with st.form("new_section_form", clear_on_submit=True):
            st.write("**Создать новый раздел:**")
            col1, col2 = st.columns([2, 1])
            with col1:
                title = st.text_input("Название")
            with col2:
                description = st.text_input("Описание")
            
            if st.form_submit_button("➕ Создать раздел"):
                if title:
                    add_section(title, description)
                    st.success(f"Раздел '{title}' создан!")
                    st.rerun()
        
        # Список всех разделов для управления
        sections_df = get_sections()
        if not sections_df.empty:
            st.write("---")
            st.write("**Все разделы:**")
            
            for _, section in sections_df.iterrows():
                col_sec, col_edit, col_del = st.columns([4, 1, 1])
                with col_sec:
                    st.write(f"**{section['title']}**")
                    if section['description']:
                        st.caption(section['description'])
                    q_count = len(get_questions(section['id']))
                    st.caption(f"Вопросов: {q_count}")
                with col_edit:
                    if st.button("✏️", key=f"edit_main_{section['id']}"):
                        st.session_state["current_section"] = section['id']
                        st.session_state["section_title"] = section['title']
                        st.session_state["editing_section"] = section['id']
                        st.rerun()
                with col_del:
                    if st.button("🗑️", key=f"del_main_{section['id']}"):
                        delete_section(section['id'])
                        st.success(f"Раздел '{section['title']}' удален!")
                        st.rerun()
        
        st.write("---")
    
    # Последние добавленные разделы
    recent_sections = get_recent_sections(limit=3)
    if not recent_sections.empty:
        st.subheader("📥 Недавно добавленные разделы")
        
        for _, section in recent_sections.iterrows():
            with st.expander(f"📁 {section['title']}", expanded=False):
                if section['description']:
                    st.write(section['description'])
                
                # Счетчик вопросов в разделе
                q_df = get_questions(section['id'])
                st.caption(f"📊 Вопросов в разделе: {len(q_df)}")
                
                # Дата создания
                if 'created_at' in section and section['created_at']:
                    st.caption(f"📅 Добавлен: {format_datetime(section['created_at'])}")
                
                # Кнопка перехода
                if st.button("Перейти в раздел →", key=f"go_to_{section['id']}", use_container_width=True):
                    st.session_state["current_section"] = section['id']
                    st.session_state["section_title"] = section['title']
                    st.rerun()
        
        st.write("---")
    
    # Последние добавленные вопросы
    recent_questions = get_recent_questions(limit=5)
    if not recent_questions.empty:
        st.subheader("🆕 Последние добавленные вопросы")
        
        for _, question in recent_questions.iterrows():
            # Форматируем дату
            date_str = ""
            if 'created_at' in question and question['created_at']:
                date_str = f" ({format_datetime(question['created_at'])})"
            
            with st.expander(f"📁 {question['section_title']} » {question['question'][:60]}...{date_str}", expanded=False):
                col_q, col_a = st.columns(2)
                
                with col_q:
                    st.markdown("**Вопрос / Ситуация**")
                    st.info(question['question'])
                
                with col_a:
                    st.markdown("**Ответ / Действия**")
                    if question['answer']:
                        st.success(question['answer'][:200] + "..." if len(question['answer']) > 200 else question['answer'])
                    else:
                        st.write("—")
                
                # Дата создания вопроса
                if 'created_at' in question and question['created_at']:
                    st.caption(f"📅 Добавлен: {format_datetime(question['created_at'])}")
                
                # Кнопка перехода в раздел
                if st.button(f"📂 Перейти в раздел '{question['section_title']}'", 
                           key=f"nav_q_{question['id']}", 
                           use_container_width=True):
                    st.session_state["current_section"] = question['section_id']
                    st.session_state["section_title"] = question['section_title']
                    st.rerun()
        
        st.write("---")
    
    # Инструкция для новых пользователей (если не админ)
    if not st.session_state.admin_logged_in:
        st.info("💡 **Совет:** Если вы администратор, войдите в систему для управления базой знаний.")