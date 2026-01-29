import os
from flask import Flask, render_template, request, redirect, session, flash, url_for
import mysql.connector
from datetime import datetime
from werkzeug.utils import secure_filename
import requests
import calendar
app = Flask(__name__)

UPLOAD_STUDY_MATERIAL = 'static/uploads/study_materials'
os.makedirs(UPLOAD_STUDY_MATERIAL, exist_ok=True)

# Required for sessions and flash messages
app.secret_key = "sba_teacher_portal_2026_secret"

# --- FILE UPLOAD CONFIGURATION ---
# This folder will store the PDFs uploaded by teachers
UPLOAD_FOLDER = 'static/uploads/homework'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Automatically create the directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Connection Helper
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="prosoftechdib.in",
            user="proso62y_root",
            password="prosoftech_root",
            database="proso62y_localhost",
            connect_timeout=5  # Add this!
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Database Connection Error: {err}")
        return None
# --- AUTHENTICATION ROUTES ---
@app.route('/sw.js')
def serve_sw():
    return app.send_static_file('sw.js')

@app.route('/')
def index():
    if 'teacher_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login_logic', methods=['POST'])
def login_logic():
    contact = request.form.get('username')
    passkey = request.form.get('password')

    db = get_db_connection()
    if db is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for('index'))

    cursor = db.cursor(dictionary=True)
    query = "SELECT * FROM teachers_dtls WHERE contact_no = %s AND passkey = %s"
    cursor.execute(query, (contact, passkey))
    teacher = cursor.fetchone()
    
    cursor.close()
    db.close()

    if teacher:
        session['teacher_id'] = teacher['contact_no']
        session['name'] = teacher['teacher_name']
        session['dept'] = teacher['dept']
        session['pic'] = teacher['pic']
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid Contact Number or Passkey.', 'danger')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- MAIN DASHBOARD ---

@app.route('/dashboard')
def dashboard():
    # 1. Access Control: Redirect to login if session doesn't exist
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    # Retrieve session data for the dashboard
    teacher_name = session.get('name')
    dept = session.get('dept')
    teacher_id = session.get('teacher_id')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # --- NEW: Fetch count of unread messages ---
        # This counts only messages where is_read is 0
        cursor.execute("SELECT COUNT(*) as unread_count FROM msg_for_teachers WHERE is_read = 0")
        result = cursor.fetchone()
        unread_count = result['unread_count'] if result else 0

        # --- EXISTING: Fetch other dashboard data ---
        # (Add any other queries you previously had here, for example:)
        # cursor.execute("SELECT * FROM some_other_table WHERE teacher_id = %s", (teacher_id,))
        # other_data = cursor.fetchall()

    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        unread_count = 0
    finally:
        cursor.close()
        db.close()

    # Pass everything to the template including the new unread_count
    return render_template('dashboard.html', 
                           name=teacher_name, 
                           dept=dept, 
                           unread_count=unread_count)

# --- ATTENDANCE MODULE ---

@app.route('/attendance', methods=['GET'])
def attendance():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    students = []
    selected_class = request.args.get('class_sel')
    selected_sec = request.args.get('sec_sel')
    selected_date = request.args.get('att_date')

    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')

    if selected_class and selected_sec:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        query = """SELECT student_name, student_rollno, mob_no 
                   FROM stu_dtls 
                   WHERE student_class = %s AND student_section = %s 
                   ORDER BY student_rollno"""
        cursor.execute(query, (selected_class, selected_sec))
        students = cursor.fetchall()
        cursor.close()
        db.close()

    return render_template('attendance.html', 
                           name=session['name'], 
                           dept=session['dept'], 
                           students=students,
                           sel_class=selected_class,
                           sel_sec=selected_sec,
                           sel_date=selected_date)

@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    att_date = request.form.get('att_date')
    att_class = request.form.get('att_class')
    present_rolls = request.form.getlist('status')
    all_rolls = request.form.getlist('all_rolls')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # 1. Save records
        for roll in all_rolls:
            status = 'P' if roll in present_rolls else 'A'
            insert_query = """INSERT INTO stu_attendance (rollno, dated, status, class, sms_status) 
                              VALUES (%s, %s, %s, %s, %s)"""
            cursor.execute(insert_query, (roll, att_date, status, att_class, 'N'))
        db.commit()

        # 2. SMS for Absentees
        absent_rolls = [r for r in all_rolls if r not in present_rolls]
        if absent_rolls:
            format_strings = ','.join(['%s'] * len(absent_rolls))
            cursor.execute(f"SELECT student_name, mob_no, student_rollno FROM stu_dtls WHERE student_rollno IN ({format_strings})", tuple(absent_rolls))
            absent_list = cursor.fetchall()

            for student in absent_list:
                mobno = student['mob_no']
                st_name = student['student_name']
                st_roll = student['student_rollno']
                message = f"Dear Parents, Your ward {st_name} is absent on {att_date}. Regards, SBA-Dib"
                
                sms_payload = {
                    "username": "prasen.prasenjit@gmail.com",
                    "apikey": "13a66e91d60169d7e69910955d8f09d1d5653882",
                    "senderid": "EDUSMS",
                    "tempid": "1507166565087200753",
                    "message": message,
                    "dest_mobileno": mobno,
                }
                try:
                    response = requests.post("http://api.edusms.co.in/api/v1/send-sms", data=sms_payload, timeout=5)
                    if response.status_code == 200:
                        update_sms_query = "UPDATE stu_attendance SET sms_status='Y' WHERE rollno=%s AND dated=%s AND status='A'"
                        cursor.execute(update_sms_query, (st_roll, att_date))
                except Exception as e:
                    print(f"SMS Error: {e}")
            db.commit()

        flash(f"Attendance saved and {len(absent_rolls)} SMS notifications sent.", "success")
    except mysql.connector.Error as err:
        db.rollback()
        flash(f"Database Error: {err}", "danger")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('dashboard'))

# --- MARKS ENTRY MODULE ---

@app.route('/marks_entry', methods=['GET'])
def marks_entry():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    students = []
    sel_class = request.args.get('class_sel')
    sel_sec = request.args.get('sec_sel')
    sel_exam = request.args.get('exam_sel')
    dept = session.get('dept')

    if sel_class and sel_sec and sel_exam:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        query = """
            SELECT s.student_rollno, s.student_name, s.student_section, s.student_class,
                   m.phy_theory, m.phy_prac, m.chem_theory, m.chem_prac, 
                   m.biol_bot, m.biol_zoo, m.bota_prac, m.zool_prac,
                   m.maths, m.engl_theory, m.alte, m.csca_theory, m.csca_prac, m.stat, m.mass
            FROM stu_dtls s
            LEFT JOIN stu_marks m ON s.student_rollno = m.student_rollno AND m.exam_name = %s
            WHERE s.student_class = %s AND s.student_section = %s
            ORDER BY s.student_rollno
        """
        cursor.execute(query, (sel_exam, sel_class, sel_sec))
        students = cursor.fetchall()
        cursor.close()
        db.close()

    return render_template('marks_entry.html', 
                           name=session['name'], 
                           dept=dept, 
                           students=students,
                           sel_class=sel_class,
                           sel_sec=sel_sec,
                           sel_exam=sel_exam)

@app.route('/submit_marks', methods=['POST'])
def submit_marks():
    if 'teacher_id' not in session: return redirect(url_for('index'))
    
    dept = session.get('dept')
    exam = request.form.get('exam_sel')
    rolls = request.form.getlist('rollno[]')
    pthy = request.form.getlist('pthy[]')
    pthp = request.form.getlist('pthp[]')
    
    db = get_db_connection()
    cursor = db.cursor()

    try:
        col_map = {
            "PHYS": ("phy_theory", "phy_prac"),
            "CHEM": ("chem_theory", "chem_prac"),
            "MATH": ("maths", None),
            "ENGL": ("engl_theory", None),
            "ALTE": ("alte", None),
            "STAT": ("stat", None),
            "CSCA": ("csca_theory", "csca_prac"),
            "MASS": ("mass", None)
        }

        for i in range(len(rolls)):
            roll = rolls[i]
            val_theory = pthy[i] if (i < len(pthy) and pthy[i]) else 0
            val_prac = pthp[i] if (i < len(pthp) and pthp[i]) else 0

            if dept in col_map:
                t_col, p_col = col_map[dept]
                if p_col:
                    sql = f"UPDATE stu_marks SET {t_col}=%s, {p_col}=%s WHERE student_rollno=%s AND exam_name=%s"
                    cursor.execute(sql, (val_theory, val_prac, roll, exam))
                else:
                    sql = f"UPDATE stu_marks SET {t_col}=%s WHERE student_rollno=%s AND exam_name=%s"
                    cursor.execute(sql, (val_theory, roll, exam))
            elif dept == "BIOL":
                b_prac = request.form.getlist('bprac[]')[i]
                z_prac = request.form.getlist('zprac[]')[i]
                sql = "UPDATE stu_marks SET biol_bot=%s, bota_prac=%s, biol_zoo=%s, zool_prac=%s WHERE student_rollno=%s AND exam_name=%s"
                cursor.execute(sql, (val_theory, b_prac, val_prac, z_prac, roll, exam))

        db.commit()
        flash(f"Marks for {dept} submitted successfully!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        db.close()
    
    return redirect(url_for('dashboard'))

# --- HOMEWORK MODULE ---

@app.route('/homework', methods=['GET', 'POST'])
def homework():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        subj = session.get('dept')
        teacher = session.get('name')
        desc = request.form.get('description', '')
        due_date = request.form.get('due_date')
        st_class = request.form.get('student_class')
        assign_date = datetime.now().strftime('%Y-%m-%d')
        
        # File handling
        file = request.files.get('hw_file')
        file_link = None
        
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            file_link = f"uploads/homework/{unique_name}"

        db = get_db_connection()
        cursor = db.cursor()
        try:
            query = """INSERT INTO stu_homework 
                       (subject_name, teacher_name, description, assigned_date, due_date, student_class, file_link) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(query, (subj, teacher, desc, assign_date, due_date, st_class, file_link))
            db.commit()
            flash("Homework assigned successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Database Error: {str(e)}", "danger")
        finally:
            cursor.close()
            db.close()
        
        return redirect(url_for('dashboard'))

    return render_template('homework.html', name=session['name'], dept=session['dept'])

# --- OTHER PLACEHOLDERS ---
@app.route('/calendar')
def academic_calendar():
    if 'teacher_id' not in session: 
        return redirect(url_for('index'))
    
    now = datetime.now()
    # Get month/year from URL args or default to current
    month = int(request.args.get('month', now.month))
    year = int(request.args.get('year', now.year))
    
    # Handle year rollover
    if month > 12: 
        month = 1; year += 1
    elif month < 1: 
        month = 12; year -= 1
        
    cal_matrix = calendar.monthcalendar(year, month)
    event_map = {}
    
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        # Fetch events for the specific month/year
        cursor.execute("SELECT DAY(dated) as d, event FROM aca_cal WHERE MONTH(dated) = %s AND YEAR(dated) = %s", (month, year))
        for row in cursor.fetchall(): 
            event_map[row['d']] = row['event']
        cursor.close()
        db.close()
    except Exception as e: 
        print(f"Calendar Error: {e}")
        
    return render_template('calendar.html', 
                           cal=cal_matrix, 
                           month=month, 
                           year=year, 
                           month_name=calendar.month_name[month], 
                           event_map=event_map, 
                           name=session.get('name'), 
                           dept=session.get('dept'))

# --- SUBMISSIONS MODULE ---

@app.route('/submissions')
def submissions():
    if 'teacher_id' not in session: 
        return redirect(url_for('index'))
    
    dept = session.get('dept')
    sel_class = request.args.get('class_sel')
    search_roll = request.args.get('search_roll')
    sel_date = request.args.get('sub_date')  # New Date Filter
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Base query
    query = "SELECT * FROM homework_submissions WHERE department = %s"
    params = [dept]
    
    if sel_class:
        query += " AND student_class = %s"
        params.append(sel_class)
        
    if search_roll:
        query += " AND roll_no LIKE %s"
        params.append(f"%{search_roll}%")
    
    if sel_date:
        # Filtering by the DATE part of the submission_date timestamp
        query += " AND DATE(submission_date) = %s"
        params.append(sel_date)
        
    query += " ORDER BY submission_date DESC"
    
    cursor.execute(query, tuple(params))
    all_submissions = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('submissions.html', 
                           submissions=all_submissions, 
                           name=session['name'], 
                           dept=dept,
                           sel_class=sel_class,
                           search_roll=search_roll,
                           sel_date=sel_date)

# --- STUDY MATERIAL MODULE ---

@app.route('/study_material', methods=['GET', 'POST'])
def study_material():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        teacher_name = session.get('name')
        dept = session.get('dept')
        topic = request.form.get('topic')
        st_class = request.form.get('student_class')
        yt_link = request.form.get('youtube_link')
        
        # File handling
        file = request.files.get('pdf_file')
        pdf_filename = None
        
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_name = f"SM_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file.save(os.path.join(UPLOAD_STUDY_MATERIAL, unique_name))
            pdf_filename = unique_name

        try:
            query = """INSERT INTO lecture_slides 
                       (teacher_name, department, subject_topic, pdf_filename, youtube_link, student_class) 
                       VALUES (%s, %s, %s, %s, %s, %s)"""
            cursor.execute(query, (teacher_name, dept, topic, pdf_filename, yt_link, st_class))
            db.commit()
            flash("Study material uploaded successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error: {str(e)}", "danger")
        
        return redirect(url_for('study_material'))

    # GET: Fetch materials uploaded by this teacher to show in a list
    cursor.execute("SELECT * FROM lecture_slides WHERE teacher_name = %s ORDER BY uploaded_at DESC", (session.get('name'),))
    materials = cursor.fetchall()
    
    cursor.close()
    db.close()
    
    return render_template('study_material.html', 
                           name=session['name'], 
                           dept=session['dept'], 
                           materials=materials)


# --- ONLINE EXAM MODULE ---

# --- ONLINE EXAM MODULE (One-by-One Upload) ---
from datetime import datetime

@app.route('/online_exam', methods=['GET', 'POST'])
def online_exam():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))
    
    teacher_name = session.get('name', 'Instructor')
    dept = session.get('dept')
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # 1. HANDLE SAVING DATA (POST)
    if request.method == 'POST':
        exam_date = request.form.get('exam_date')  # YYYY-MM-DD
        st_class = request.form.get('student_class')
        q_no = request.form.get('q_no')
        correct_ans = request.form.get('correct_ans')
        upload_type = request.form.get('upload_type')
        
        q_text = request.form.get('q_text_content') if upload_type == 'text' else None
        filename = None

        if upload_type == 'file':
            file = request.files.get('question_img')
            if file and file.filename != '':
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"Q_{exam_date}_{st_class}_{q_no}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        try:
            # A. Save to exam_questions (The content)
            cursor.execute("""INSERT INTO exam_questions (dated, sub, class, qno, question_file, question_text) 
                           VALUES (%s, %s, %s, %s, %s, %s)""", 
                           (exam_date, dept, st_class, q_no, filename, q_text))
            
            # B. Save to answerkey (Your Schema)
            cursor.execute("""INSERT INTO answerkey (dated, sub, qno, ans, class) 
                           VALUES (%s, %s, %s, %s, %s)""",
                           (exam_date, dept, q_no, correct_ans, st_class))
            
            # C. Check if we need to update qnos or add to aca_cal
            cursor.execute("SELECT qnos FROM qnos WHERE dated=%s AND sub=%s AND class=%s", (exam_date, dept, st_class))
            qnos_record = cursor.fetchone()
            
            if not qnos_record:
                # First question for this exam: Add to qnos and aca_cal
                cursor.execute("INSERT INTO qnos (dated, sub, qnos, class) VALUES (%s, %s, %s, %s)", (exam_date, dept, 1, st_class))
                
                # Update Academic Calendar (Match your schema: slno, dated, day, event)
                day_name = datetime.strptime(exam_date, '%Y-%m-%d').strftime('%A')
                cursor.execute("INSERT INTO aca_cal (dated, day, event) VALUES (%s, %s, %s)", 
                               (exam_date, day_name, f"Exam: {dept} (Cl {st_class})"))
            else:
                # Increment existing count
                cursor.execute("UPDATE qnos SET qnos = qnos + 1 WHERE dated=%s AND sub=%s AND class=%s", (exam_date, dept, st_class))

            db.commit()
            flash(f"Question {q_no} successfully saved!", "success")
        except Exception as e:
            db.rollback()
            print(f"Error: {e}") # Check your terminal/console for this
            flash("Database Error. Check if Question Number already exists.", "danger")
        
        return redirect(url_for('online_exam', date=exam_date, cls=st_class))

    # 2. HANDLE PREVIEW (GET)
    sel_date = request.args.get('date', '')
    sel_cls = request.args.get('cls', '')
    uploaded_qs = []

    if sel_date and sel_cls:
        # Join exam_questions with answerkey so we can show the correct answer in the table
        cursor.execute("""
            SELECT eq.*, ak.ans 
            FROM exam_questions eq
            INNER JOIN answerkey ak ON eq.dated = ak.dated AND eq.qno = ak.qno AND eq.class = ak.class
            WHERE eq.dated=%s AND eq.class=%s AND eq.sub=%s 
            ORDER BY CAST(eq.qno AS UNSIGNED) ASC
        """, (sel_date, sel_cls, dept))
        uploaded_qs = cursor.fetchall()

    db.close()
    return render_template('online_exam.html', name=teacher_name, dept=dept, 
                           uploaded_qs=uploaded_qs, sel_date=sel_date, sel_cls=sel_cls)

from datetime import datetime

@app.route('/online_class', methods=['GET', 'POST'])
def online_class():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))
    
    teacher_name = session.get('name')
    dept = session.get('dept')
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        c_date = request.form.get('class_date') # e.g., 2026-01-25
        c_time = request.form.get('class_time') # e.g., 10:30
        st_class = request.form.get('student_class')
        zoom_link = request.form.get('zoom_link')

        # Combine Date and Time for your DATETIME column
        full_datetime = f"{c_date} {c_time}:00"

        try:
            # 1. Insert into your existing online_classes table
            cursor.execute("""
                INSERT INTO online_classes 
                (subject_name, instructor, class_time, zoom_link, student_class) 
                VALUES (%s, %s, %s, %s, %s)
            """, (dept, teacher_name, full_datetime, zoom_link, st_class))
            
            # 2. Add to Academic Calendar (aca_cal)
            # We use 'Live Class' prefix so the calendar can identify and color it blue/green
            day_name = datetime.strptime(c_date, '%Y-%m-%d').strftime('%A')
            event_desc = f"Live Class: {dept} ({c_time})"
            cursor.execute("INSERT INTO aca_cal (dated, day, event) VALUES (%s, %s, %s)", 
                           (c_date, day_name, event_desc))

            db.commit()
            flash(f"Live Class scheduled for {st_class}!", "success")
        except Exception as e:
            db.rollback()
            print(f"Error: {e}")
            flash("Error scheduling class. Please check your data.", "danger")
        
        return redirect(url_for('online_class'))

    # Fetch history for the logged-in teacher
    cursor.execute("""
        SELECT * FROM online_classes 
        WHERE instructor=%s 
        ORDER BY class_time DESC
    """, (teacher_name,))
    history = cursor.fetchall()
    
    db.close()
    return render_template('online_class.html', name=teacher_name, dept=dept, history=history)


# --- MESSAGES MODULE ---

@app.route('/messages', methods=['GET', 'POST'])
def messages():
    # 1. Access Control: Redirect to login if session doesn't exist
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    teacher_name = session.get('name')
    dept = session.get('dept')
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        # Teacher sending message to students
        msg_text = request.form.get('student_msg')
        # We include the teacher's name and dept automatically from the session
        msg_date = datetime.now().strftime('%Y-%m-%d')
        msg_time = datetime.now().strftime('%H:%M:%S')

        try:
            query = """INSERT INTO msg_to_students (teachr_name, dept, msg_date, msg_time, msg_dtls) 
                       VALUES (%s, %s, %s, %s, %s)"""
            cursor.execute(query, (teacher_name, dept, msg_date, msg_time, msg_text))
            db.commit()
            flash("Message sent to students successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error: {str(e)}", "danger")
        
        return redirect(url_for('messages'))

    # GET: Fetch Admin Messages for this teacher
    cursor.execute("SELECT * FROM msg_for_teachers ORDER BY dated DESC, timer DESC")
    admin_messages = cursor.fetchall()

    # GET: Fetch only this teacher's sent message history
    cursor.execute("""SELECT * FROM msg_to_students 
                      WHERE teachr_name = %s ORDER BY msg_date DESC, msg_time DESC""", (teacher_name,))
    sent_messages = cursor.fetchall()

    cursor.close()
    db.close()
    return render_template('messages.html', 
                           admin_msgs=admin_messages, 
                           sent_msgs=sent_messages, 
                           name=teacher_name, 
                           dept=dept)
# --- SETTINGS / PROFILE MODULE ---

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'teacher_id' not in session:
        return redirect(url_for('index'))

    teacher_id = session['teacher_id']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        new_name = request.form.get('teacher_name')
        new_dept = request.form.get('dept')
        new_passkey = request.form.get('passkey')
        
        # Handle Profile Picture Upload
        file = request.files.get('pic')
        pic_filename = session.get('pic') # Keep old pic if no new one uploaded

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            # Create a unique name using teacher ID to avoid conflicts
            pic_filename = f"profile_{teacher_id}_{filename}"
            file.save(os.path.join('static/uploads/profiles', pic_filename))
            # Ensure the directory exists
            os.makedirs('static/uploads/profiles', exist_ok=True)

        try:
            query = """UPDATE teachers_dtls 
                       SET teacher_name = %s, dept = %s, passkey = %s, pic = %s 
                       WHERE contact_no = %s"""
            cursor.execute(query, (new_name, new_dept, new_passkey, pic_filename, teacher_id))
            db.commit()

            # Update Session Data so changes reflect immediately
            session['name'] = new_name
            session['dept'] = new_dept
            session['pic'] = pic_filename
            
            flash("Profile updated successfully!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error updating profile: {str(e)}", "danger")
        
        return redirect(url_for('settings'))

    # GET: Fetch current teacher details
    cursor.execute("SELECT * FROM teachers_dtls WHERE contact_no = %s", (teacher_id,))
    teacher_data = cursor.fetchone()
    cursor.close()
    db.close()

    return render_template('settings.html', 
                           teacher=teacher_data, 
                           name=session['name'], 
                           dept=session['dept'])

if __name__ == "__main__":
    # Use the PORT provided by Google Cloud, or default to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)