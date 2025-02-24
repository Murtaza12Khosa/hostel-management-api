from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_mysqldb import MySQL
import hashlib
import datetime
import re
import bcrypt
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_caching import Cache

app = Flask(__name__)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Set your MySQL password
app.config['MYSQL_DB'] = 'hostel_management_app'
app.config["MYSQL_POOL_RECYCLE"] = 300
app.config["MYSQL_POOL_SIZE"] = 10  # Connection pooling

mysql = MySQL(app)
cache = Cache(app, config={"CACHE_TYPE": "simple"})  # Simple in-memory cache

CORS(app, origins=["http://localhost:3000"])


# Example route for registration (adjust as needed)
# Gmail SMTP Configuration
GMAIL_USER = "murtaza@gmail.com"
GMAIL_PASS = ""  # Generate from Google App Passwords

def send_confirmation_email(first_name, email):
    msg = MIMEText(f"Hello {first_name},\n\nThank you for registering at our hostel management system.")
    msg["Subject"] = "Welcome to Hostel Management App!"
    msg["From"] = GMAIL_USER
    msg["To"] = email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, email, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

def is_valid_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@gmail\.com$', email)

def is_valid_contact(contact_number):
    return re.match(r'^\d{10}$', contact_number)  # Assumes a 10-digit phone number

def is_strong_password(password):
    return len(password) >= 8 and any(c.isdigit() for c in password) and any(c.isalpha() for c in password)

@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.get_json()

    first_name = data.get('first_name')
    middle_name = data.get('middle_name', '')
    last_name = data.get('last_name')
    gender = data.get('gender')   
    contact_number = data.get('contact_number')
    email = data.get('email')
    password = data.get('password')

    # Validate required fields
    if not all([first_name, last_name, gender, contact_number, email, password]):
        return jsonify({'message': 'All fields are required'}), 400

    # Validate email format
    if not is_valid_email(email):
        return jsonify({'message': 'Invalid email format. Only Gmail addresses are allowed'}), 400
    
    # Validate contact number
    if not is_valid_contact(contact_number):
        return jsonify({'message': 'Invalid contact number. Must be 10 digits'}), 400
    
    # Validate password strength
    if not is_strong_password(password):
        return jsonify({'message': 'Password must be at least 8 characters long, contain both letters and numbers'}), 400
    
    
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('''
            INSERT INTO registration (first_name, middle_name, last_name, gender, contact_number, email, password, registration_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ''', (first_name, middle_name, last_name, gender, contact_number, email, password))

        mysql.connection.commit()
        cursor.close()

        # Send confirmation email
        send_confirmation_email(first_name, email)

        return jsonify({'message': 'Registration successful. Confirmation email sent.'}), 201

    except Exception as e:
        mysql.connection.rollback()
        cursor.close()
        return jsonify({'message': f'Error: {str(e)}'}), 500

@app.route('/api/user_login', methods=['POST'])
def user_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    # Hash the password (optional, for better security)

    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            return jsonify({"message": "Login successful!"}), 200
        else:
            return jsonify({"message": "Invalid credentials, please try again."}), 401
    except Exception as e:
        return jsonify({"message": "An error occurred: " + str(e)}), 500
    
    
def is_valid_course_name(course_name):
    return isinstance(course_name, str) and len(course_name) > 1

def is_valid_course_code(course_code):
    return re.match(r'^[A-Z0-9]{3,10}$', course_code)  # Example: ABC123

def is_valid_course_duration(course_duration):
    return isinstance(course_duration, int) and course_duration > 0

@app.route('/api/courses', methods=['GET'])
@cache.cached(timeout=600, query_string=True)  # Cache results for 10 minutes
def get_courses():
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        course_name = request.args.get("course_name")
        course_code = request.args.get("course_code")
        course_duration = request.args.get("course_duration")

        # Optimized SQL query with SQL_CALC_FOUND_ROWS
        query = """
            SELECT SQL_CALC_FOUND_ROWS id, course_name, course_code, course_duration 
            FROM courses WHERE 1=1
        """
        values = []

        if course_name:
            query += " AND course_name LIKE %s"
            values.append(f"%{course_name}%")
        if course_code:
            query += " AND course_code = %s"
            values.append(course_code)
        if course_duration:
            query += " AND course_duration = %s"
            values.append(course_duration)

        query += " LIMIT %s OFFSET %s"
        values.append(per_page)
        values.append(offset)

        cursor = mysql.connection.cursor()
        cursor.execute(query, values)
        courses = cursor.fetchall()

        # Get total records in a single call
        cursor.execute("SELECT FOUND_ROWS()")
        total_record = cursor.fetchone()[0]
        cursor.close()

        if not courses:
            return jsonify({"message": "No courses found", "data": []}), 200

        result = [
            {"id": course[0], "course_name": course[1], "course_code": course[2], "course_duration": course[3]}
            for course in courses
        ]

        total_page = (total_record + per_page - 1) // per_page

        return jsonify({
            "data": result,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_page": total_page,
                "total_record": total_record
            }
        })

    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500

@app.route('/api/courses', methods=['POST'])
def add_course():
    data = request.get_json()
    
    if not is_valid_course_name(data.get("course_name")):
        return jsonify({'message': 'Invalid course name'}), 400
    if not is_valid_course_code(data.get("course_code")):
        return jsonify({'message': 'Invalid course code. Use uppercase letters and numbers (3-10 characters).'}), 400
    if not is_valid_course_duration(data.get("course_duration")):
        return jsonify({'message': 'Invalid course duration. Must be a positive integer.'}), 400

    cursor = mysql.connection.cursor()
    cursor.execute("INSERT INTO courses (course_name, course_code, course_duration) VALUES (%s, %s, %s)",
                   (data['course_name'], data['course_code'], data['course_duration']))
    mysql.connection.commit()
    return jsonify({'message': 'Course added successfully', 'data': data})

@app.route('/api/courses/<string:course_code>', methods=['DELETE'])
def delete_course(course_code):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id FROM courses WHERE course_code = %s", (course_code,))
    existing_course = cursor.fetchone()
    
    if not existing_course:
        return jsonify({'message': 'Course code not found'}), 404
    
    cursor.execute("DELETE FROM courses WHERE course_code = %s", (course_code,))
    mysql.connection.commit()
    cursor.close()
    return jsonify({'message': 'Course deleted successfully'}), 200

@app.route('/api/courses/<string:course_code>', methods=['PUT'])
def update_course(course_code):
    data = request.json
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id FROM courses WHERE course_code = %s", (course_code,))
    existing_course = cursor.fetchone()
    
    if not existing_course:
        return jsonify({'message': 'Course code not found'}), 404
    
    if not is_valid_course_name(data.get("course_name")):
        return jsonify({'message': 'Invalid course name'}), 400
    if not is_valid_course_code(data.get("course_code")):
        return jsonify({'message': 'Invalid course code. Use uppercase letters and numbers (3-10 characters).'}), 400
    if not is_valid_course_duration(data.get("course_duration")):
        return jsonify({'message': 'Invalid course duration. Must be a positive integer.'}), 400

    cursor.execute(
        "UPDATE courses SET course_name=%s, course_code=%s, course_duration=%s WHERE course_code=%s",
        (data["course_name"], data["course_code"], data["course_duration"], course_code),
    )
    mysql.connection.commit()
    cursor.close()
    return jsonify({'message': 'Course updated successfully'}), 200




def is_valid_room_number(room_number):
    return isinstance(room_number, str) and room_number.strip() != ""

def is_valid_room_type(room_type):
    return isinstance(room_type, str) and room_type.strip() != ""

def is_valid_capacity(capacity):
    return isinstance(capacity, int) and capacity > 0

def is_valid_price(price):
    return isinstance(price, (int, float)) and price >= 0

def is_valid_status(status):
    return status in ["available", "occupied", "maintenance"]

# 🔹 Get All Rooms
@app.route('/api/room', methods=['GET'])
def get_rooms():
    try:
        
        page = request.args.get("page", default=1 , type=int)
        per_page = 50
        offset = (page -1) * per_page
        
        room_id = request.args.get('room_id')
        room_number = request.args.get('room_number')
        room_type = request.args.get('room_type')
        capacity = request.args.get('capacity')
        per_day = request.args.get('per_day')
        per_week = request.args.get('per_week')
        per_month = request.args.get('per_month')
        status = request.args.get('status')
        
        query = "SELECT room_id,room_number,room_type,capacity,per_day,per_week,per_month,status FROM room WHERE 1=1"
        values = []
        #applying filter
        if room_id:
            query += " AND room_id = %s"
            values.append(room_id)
        if room_number:
            query += " AND room_number = %s"
            values.append(room_number)
        if room_type:
            query += " AND room_type =%s"
            values.append(room_type)
        if capacity:
            query += " AND capacity = %s"
            values.append(capacity)
        if per_day:
            query += " AND per_day =%s"
            values.append(per_day)
        if per_week:
            query += " AND per_week =%s"
            values.append(per_week)
        if per_month:
            query += " AND per_month =%s"
            values.append(per_month)
        if status:
            query += " AND status = %s"
            values.append(status)
            
        query += " LIMIT %s OFFSET %s"    
        values.append(per_page)
        values.append( offset)
        
        cursor = mysql.connection.cursor()
        cursor.execute(query,values)
        rooms = cursor.fetchall()

        count_query = "SELECT COUNT(*) FROM room WHERE 1=1"
        cursor.execute(count_query)
        total_record = cursor.fetchone()[0]
        cursor.close()
        
        
        
        if not rooms:
            return jsonify({"message": "No rooms available", "data": []}), 200

        result = [
            {
                "room_id": room[0],
                "room_number": room[1],
                "room_type": room[2],
                "capacity": room[3],
                "per_day": room[4],
                "per_week": room[5],
                "per_month": room[6],
                "status": room[7]
            }
            for room in rooms
        ]
        
        total_page = (total_record + per_page -1) //per_page
        
        return jsonify({
            "data" : result,
            "pagination": {
                "current page" : page,
                "per_page" : per_page,
                "total_page" : total_page,
                "total_record" : total_record
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 Add Room
@app.route('/api/room', methods=['POST'])
def add_room():
    try:
        data = request.json
        room_number = data.get('room_number')
        room_type = data.get('room_type')
        capacity = data.get('capacity')
        per_day = data.get('per_day')
        per_week = data.get('per_week')
        per_month = data.get('per_month')
        status = data.get('status')

        if not all([room_number, room_type, capacity, per_day, per_week, per_month, status]):
            return jsonify({"error": "All fields are required"}), 400
        
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO room (room_number, room_type, capacity, per_day, per_week, per_month, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (room_number, room_type, capacity, per_day, per_week, per_month, status))
        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Room added successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 🔹 Update Room
@app.route('/api/room/<string:room_number>', methods=['PUT'])
def update_room(room_number):
    try:
        data = request.json
        room_type = data.get('room_type')
        capacity = data.get('capacity')
        per_day = data.get('per_day')
        per_week = data.get('per_week')
        per_month = data.get('per_month')
        status = data.get('status')

        # Check if room exists based on room_number
        cur = mysql.connection.cursor()
        cur.execute("SELECT room_id FROM room WHERE room_number = %s", (room_number,))
        existing_room = cur.fetchone()

        if not existing_room:
            return jsonify({"error": "Room number not found"}), 404
        
        if not all([room_type, capacity, per_day, per_week, per_month, status]):
            return jsonify({"error": "All fields are required"}), 400
        if not is_valid_room_type(room_type):
            return jsonify({"error": "Invalid room type"}), 400
        if not is_valid_capacity(capacity):
            return jsonify({"error": "Invalid capacity. Must be a positive integer."}), 400
        if not is_valid_price(per_day) or not is_valid_price(per_week) or not is_valid_price(per_month):
            return jsonify({"error": "Invalid pricing. Prices must be non-negative numbers."}), 400
        if not is_valid_status(status):
            return jsonify({"error": "Invalid status. Must be 'available', 'occupied', 'maintenance', or 'booked'."}), 400


        room_id = existing_room[0]  # Get room_id from the existing room
        cur.execute("""
            UPDATE room 
            SET room_type=%s, capacity=%s, per_day=%s, per_week=%s, per_month=%s, status=%s 
            WHERE room_number=%s
        """, (room_type, capacity, per_day, per_week, per_month, status, room_number))
        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Room updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 🔹 Delete Room Route
@app.route('/api/room/<string:room_number>', methods=['DELETE'])
def delete_room(room_number):
    try:
        # Check if room exists based on room_number
        cur = mysql.connection.cursor()
        cur.execute("SELECT room_id FROM room WHERE room_number = %s", (room_number,))
        existing_room = cur.fetchone()
        
        if not existing_room:
            return jsonify({"error": "Room number not found"}), 404

        room_id = existing_room[0]  # Get room_id from the existing room
        cur.execute("DELETE FROM room WHERE room_number = %s", (room_number,))
        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Room deleted successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
    
@app.route('/get_students', methods=['GET'])
def get_students():
    try:
        
        student_id = request.args.get("student_id")
        full_name = request.args.get("full_name")
        course = request.args.get("course")
        room_number = request.args.get("room_number")
        status = request.args.get("status")
        
        query = "SELECT student_id, full_name, course, room_number, status FROM student WHERE 1=1"
        values = []
        
        if student_id:
            query += " AND student_id = %s"
            values.append(student_id)
        if full_name:
            query += " AND full_name = %s"
            values.append(full_name)
        if course:
            query += " AND course = %s"
            values.append(course)
        if room_number:
            query += " AND room_number = %s"
            values.append(room_number)
        if status:
            query += " AND status = %s"
            values.append(status)
        
        cursor = mysql.connection.cursor()
        cursor.execute(query, values)
        students = cursor.fetchall()
        cursor.close()
        
        # Convert list of tuples into a list of dictionaries
        student_list = [
            {
                "student_id": row[0],
                "full_name": row[1],
                "course": row[2],
                "room_number": row[3],
                "status": row[4]
            } 
            for row in students
        ]
        
        return jsonify(student_list)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
    
    
    
# Route to register a new student into the 'student_registration' table
# Register a new student@app.route('/register_student', methods=['POST'])
@app.route('/register_student', methods=['POST'])
def register_student():
    data = request.get_json()  # Get the JSON data sent from React
    print(data)  # Log to verify data is being received
    # Insert data into the database here
    # Make sure your SQL query matches the structure of your database
    try:
        cursor = mysql.connection.cursor()
        query = """INSERT INTO student_registration (room_number, seater, fees, food_status, stay_from, duration, 
                  room_type, course, first_name, middle_name, last_name, gender, contact_no, email, 
                  address, city, state, zip) 
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(query, (
            data['room_number'], data['seater'], data['fees'], data['food_status'], 
            data['stay_from'], data['duration'], data['room_type'], data['course'], 
            data['first_name'], data['middle_name'], data['last_name'], data['gender'], 
            data['contact_no'], data['email'], data['address'], data['city'], 
            data['state'], data['zip']
        ))
        mysql.connection.commit()  # Commit the transaction to save the data
        cursor.close()
        return jsonify({'message': 'Student registered successfully!'}), 201
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'An error occurred while saving the student data'}), 500



# Function to validate if a string is not empty
def is_valid_string(value):
    return isinstance(value, str) and value.strip() != ""

# Function to validate email format
def is_valid_email(email):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email) is not None

# Route to fetch registration data
@app.route('/get_registration_data', methods=['GET'])
def get_registration_data():
    try:
        page = request.args.get("page" , default= 1 , type= int)
        per_page = 10
        offset = (page -1  ) * per_page
        
        id = request.args.get("id")
        first_name = request.args.get("first_name")
        middle_name = request.args.get("middle_name")
        last_name = request.args.get("last_name")
        email = request.args.get("email")
        registration_date = request.args.get("registration_date")
        
        query = "SELECT id, first_name, middle_name, last_name, email, registration_date FROM registration WHERE 1=1"
        values = []
        
        if id:
            query += " AND id = %s"
            values.append(id)
        if first_name:
            query += " AND first_name = %s"
            values.append(first_name)
        if middle_name:
            query += " AND middle_name = %s"
            values.append(middle_name)
        if last_name:
            query += " AND last_name = %s"
            values.append(last_name)
        if email:
            query += " AND email = %s"
            values.append(email)
        if registration_date:
            query += " AND registration_date = %s"
            values.append(registration_date)
            
        query += " LIMIT %s OFFSET %s"
        values.append(per_page)
        values.append(offset)
            
            
        cursor = mysql.connection.cursor()
        
        count_query = "SELECT COUNT(*) FROM registration WHERE 1=1"
        cursor.execute(count_query)
        total_record = cursor.fetchone()[0]
        
        # Execute query
        cursor.execute(query, values)
        registration_data = cursor.fetchall()
        
        # Convert result to JSON-serializable format (list of dictionaries)
        result = [
            {
                "id": row[0],
                "first_name": row[1],
                "middle_name": row[2],
                "last_name": row[3],
                "email": row[4],
                "registration_date": row[5]
            }
            for row in registration_data
        ]
        
        total_page = (total_record + per_page - 1  ) // per_page
        cursor.close()
        
        
        return jsonify({
            "data" : result,
            "pagination": {
                "current Page" : page,
                "per_page": per_page,
                "total_page" :total_page,
                "total_record" : total_record
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

   
    
   

# Route to delete a user by id
@app.route("/remove_log/<int:id>", methods=["DELETE"])
def remove_access_log(id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM registration WHERE id = %s", (id,))
        mysql.connection.commit()
        cursor.close()
        return jsonify({"message": "Log removed successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to update user data by id
@app.route("/update_log/<int:id>", methods=["PUT"])
def update_access_log(id):
    try:
        data = request.get_json()
        first_name = data.get("first_name")
        middle_name = data.get("middle_name")
        last_name = data.get("last_name")
        email = data.get("email")

        # Validation checks
        if not all([first_name, last_name, email]):
            return jsonify({"error": "First name, last name, and email are required."}), 400
        if not is_valid_string(first_name) or not is_valid_string(last_name):
            return jsonify({"error": "First and last name must be non-empty strings."}), 400
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format."}), 400

        cursor = mysql.connection.cursor()
        cursor.execute("""
            UPDATE registration 
            SET first_name = %s, middle_name = %s, last_name = %s, email = %s 
            WHERE id = %s
        """, (first_name, middle_name, last_name, email, id))
        mysql.connection.commit()
        cursor.close()

        return jsonify({"message": "User updated successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
    
    

# Function to validate if a string is not empty
def is_valid_string(value):
    return isinstance(value, str) and value.strip() != ""

# Function to validate if room number is a positive integer
def is_valid_room_number(room_number):
    return isinstance(room_number, int) and room_number > 0

# Function to validate status
def is_valid_status(status):
    return status in ['available', 'occupied', 'maintenance']

# Update student information (only specific fields)
@app.route('/update_student', methods=['POST'])
def update_student():
    data = request.get_json()
    student_id = data.get('student_id')
    
    # Ensure required fields are provided
    full_name = data.get('full_name')
    course = data.get('course')
    room_number = data.get('room_number')
    status = data.get('status')

    # Validation checks
    if not all([student_id, full_name, course, room_number, status]):
        return jsonify({"error": "All fields (student_id, full_name, course, room_number, status) are required."}), 400

    if not is_valid_string(full_name):
        return jsonify({"error": "Full name must be a non-empty string."}), 400

    if not is_valid_string(course):
        return jsonify({"error": "Course must be a non-empty string."}), 400

    if not is_valid_room_number(room_number):
        return jsonify({"error": "Room number must be a positive integer."}), 400

    if not is_valid_status(status):
        return jsonify({"error": "Invalid status. Must be 'available', 'occupied', or 'maintenance'."}), 400
    
    # Using cursor from MySQL connection
    cursor = mysql.connection.cursor()

    # Update logic using student_id and the specific data fields
    query = """
        UPDATE student
        SET full_name = %s, course = %s, room_number = %s, status = %s
        WHERE student_id = %s
    """
    
    cursor.execute(query, (full_name, course, room_number, status, student_id))
    
    mysql.connection.commit()
    cursor.close()

    return jsonify({"message": "Student updated successfully!"})

# Delete student
@app.route('/delete_student/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    # Delete logic using student_id
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM student WHERE student_id = %s", [student_id])
    mysql.connection.commit()
    cursor.close()
    return jsonify({"message": "Student deleted successfully!"})



# Function to validate email format
def is_valid_email(email):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email) is not None

# Function to validate if a string is not empty
def is_valid_string(value):
    return isinstance(value, str) and value.strip() != ""

# Function to validate feedback type
def is_valid_feedback_type(feedback_type):
    valid_feedback_types = ["suggestion", "complaint", "praise", "other"]
    return feedback_type in valid_feedback_types

# Route to fetch feedback
@app.route("/api/feedback", methods=["GET"])
def get_feedback():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, feedback_type, feedback_message, email, submitted_at FROM feedback")
    feedback = cur.fetchall()
    cur.close()

    if not feedback:
        return jsonify({"error": "No feedback found."}), 404

    return jsonify([
        {
            "id": row[0],
            "type": row[1],  
            "message": row[2],  
            "email": row[3],  
            "date_submitted": row[4].strftime('%Y-%m-%d %H:%M:%S')  # Convert timestamp to string
        }
        for row in feedback
    ])

# Route to delete feedback
@app.route("/api/feedback/<int:id>", methods=["DELETE"])
def delete_feedback(id):
    # Validate that the feedback ID exists
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM feedback WHERE id = %s", (id,))
    feedback = cur.fetchone()
    
    if not feedback:
        return jsonify({"error": "Feedback not found."}), 404
    
    # Delete feedback from database
    cur.execute("DELETE FROM feedback WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Feedback deleted successfully"}), 200




# Helper function to validate complaint status
def is_valid_complaint_status(status):
    return status in ["pending", "resolved", "in-progress", "closed"]

# Route to get all complaints
@app.route("/api/complaints", methods=["GET"])
def get_complaints():
    try:
        # Pagination parameters
        page = request.args.get("page", default=1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        # Base query
        query = "SELECT id, name, email, subject, category, message, created_at, status FROM complaints WHERE 1=1"
        values = []

        # Filters
        id = request.args.get("id")
        name = request.args.get("name")
        email = request.args.get("email")
        subject = request.args.get("subject")
        category = request.args.get("category")
        message = request.args.get("message")
        created_at = request.args.get("created_at")
        status = request.args.get("status")

        if id:
            query += " AND id=%s"
            values.append(id)
        if name:
            query += " AND name = %s"
            values.append(name)
        if email:
            query += " AND email = %s"
            values.append(email)
        if subject:
            query += " AND subject = %s"
            values.append(subject)
        if category:
            query += " AND category = %s"
            values.append(category)
        if message:
            query += " AND message = %s"
            values.append(message)
        if created_at:
            query += " AND created_at = %s"
            values.append(created_at)
        if status:
            query += " AND status = %s"
            values.append(status)

        # Add pagination
        query += " LIMIT %s OFFSET %s"
        values.append(per_page)
        values.append(offset)

        # Execute the query
        cur = mysql.connection.cursor()
        cur.execute(query, values)
        complaints = cur.fetchall()

        # Convert results into JSON format
        complaints_list = [
            {
                "id": complaint[0],
                "name": complaint[1],
                "email": complaint[2],
                "subject": complaint[3],
                "category": complaint[4],
                "message": complaint[5],
                "created_at": complaint[6],
                "status": complaint[7]
            }
            for complaint in complaints
        ]

        # Get total number of records for pagination
        count_query = "SELECT COUNT(*) FROM complaints WHERE 1=1"
        cur.execute(count_query)
        total_record = cur.fetchone()[0]
        cur.close()

        total_pages = (total_record + per_page - 1) // per_page

        return jsonify({
            'data': complaints_list,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_records': total_record,
                'total_pages': total_pages
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Update complaint status with validation
@app.route("/api/complaints/<int:complaint_id>", methods=["PUT"])
def update_complaint_status(complaint_id):
    data = request.json
    new_status = data.get("status")

    # Validate the new status
    if not new_status:
        return jsonify({"error": "Status is required"}), 400

    if not is_valid_complaint_status(new_status):
        return jsonify({"error": "Invalid status. Must be one of 'pending', 'resolved', 'in-progress', or 'closed'."}), 400

    # Check if the complaint exists
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM complaints WHERE id = %s", (complaint_id,))
    existing_complaint = cur.fetchone()

    if not existing_complaint:
        return jsonify({"error": "Complaint not found."}), 404

    # Update the complaint status
    cur.execute("UPDATE complaints SET status = %s WHERE id = %s", (new_status, complaint_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Complaint status updated successfully"})

# Delete complaint
@app.route("/api/complaints/<int:complaint_id>", methods=["DELETE"])
def delete_complaint(complaint_id):
    # Check if the complaint exists
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM complaints WHERE id = %s", (complaint_id,))
    existing_complaint = cur.fetchone()

    if not existing_complaint:
        return jsonify({"error": "Complaint not found."}), 404

    # Delete the complaint
    cur.execute("DELETE FROM complaints WHERE id = %s", (complaint_id,))
    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Complaint deleted successfully"})



import re
from datetime import datetime

# Function to validate email format
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Function to validate phone number format
def is_valid_phone(phone):
    return len(phone) == 11 and phone.isdigit()

# Function to validate guardian contact number format
def is_valid_guardian_contact_no(guardian_contact_no):
    return len(guardian_contact_no) == 11 and guardian_contact_no.isdigit()

# Function to validate food status
def is_valid_food_status(food_status):
    return food_status in ['yes', 'no']

# Function to validate date format (stay_from)
def is_valid_date(date_string):
    try:
        datetime.strptime(date_string, '%Y-%m-%d')  # Example: '2025-02-06'
        return True
    except ValueError:
        return False

# Function to validate gender
def is_valid_gender(gender):
    return gender in ["male", "female", "other"]

# Route to book hostel with validation
@app.route('/api/book_hostel', methods=['POST'])
def book_hostel():
    try:
        # Get data from the form submission (JSON format)
        data = request.get_json()

        # Extract form data
        room_no = data.get("room_no")
        seater = data.get("seater")
        fees = data.get("fees")
        food_status = data.get("food_status")
        stay_from = data.get("stay_from")
        stay_duration = data.get("stay_duration")
        course = data.get("course")
        first_name = data.get("first_name")
        middle_name = data.get("middle_name")
        last_name = data.get("last_name")
        gender = data.get("gender")
        phone = data.get("phone")
        email = data.get("email")
        guardian_name = data.get("guardian_name")
        guardian_relation = data.get("guardian_relation")
        guardian_contact_no = data.get("guardian_contact_no")
        address = data.get("address")
        city = data.get("city")
        state = data.get("state")

        # Validation checks

        # Ensure all required fields are provided
        required_fields = [room_no, seater, fees, food_status, stay_from, stay_duration, course, 
                           first_name, last_name, gender, phone, email, guardian_name, 
                           guardian_relation, guardian_contact_no, address, city, state]

        if any(field is None for field in required_fields):
            return jsonify({"error": "Missing required field(s)."}), 400

        # Validate email format
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format."}), 400

        # Validate phone number format
        if not is_valid_phone(phone):
            return jsonify({"error": "Phone number must be exactly 11 digits and numeric."}), 400

        # Validate guardian contact number format
        if not is_valid_guardian_contact_no(guardian_contact_no):
            return jsonify({"error": "Guardian contact number must be exactly 11 digits and numeric."}), 400

        # Validate gender
        if not is_valid_gender(gender):
            return jsonify({"error": "Gender must be 'male', 'female', or 'other'."}), 400

        # Validate food_status
        if not is_valid_food_status(food_status):
            return jsonify({"error": "Invalid food_status. Must be 'With Food ' or 'Without Food'."}), 400

        # Validate date format for 'stay_from'
        if not is_valid_date(stay_from):
            return jsonify({"error": "Invalid date format for 'stay_from'. Expected format: YYYY-MM-DD."}), 400

        # Validate 'stay_duration' is a positive integer
        if not isinstance(stay_duration, int) or stay_duration <= 0:
            return jsonify({"error": "'stay_duration' must be a positive integer."}), 400

        # Connect to the database
        cur = mysql.connection.cursor()

        # Insert the data into the 'book_hostel' table
        cur.execute("""
            INSERT INTO book_hostel 
            (room_no, seater, fees, food_status, stay_from, stay_duration, course, 
            first_name, middle_name, last_name, gender, phone, email, guardian_name, 
            guardian_relation, guardian_contact_no, address, city, state) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (room_no, seater, fees, food_status, stay_from, stay_duration, course, 
              first_name, middle_name, last_name, gender, phone, email, guardian_name, 
              guardian_relation, guardian_contact_no, address, city, state))

        # Commit the transaction
        mysql.connection.commit()

        # Close the cursor
        cur.close()

        # Return a success message
        return jsonify({"message": "Hostel booked successfully!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/rooms', methods=['GET'])
def rooms():
    try:
        # Get filter parameters from URL query
        room_id = request.args.get("room_id")
        room_number = request.args.get("room_number")
        room_type = request.args.get("room_type")
        capacity = request.args.get("capacity")
        per_day = request.args.get("per_day")
        per_week = request.args.get("per_week")
        per_month = request.args.get("per_month")
        status = request.args.get("status")
        
        # Pagination parameters
        page = request.args.get("page", default=1, type=int)  # Default page = 1
        per_page = 50  # Number of records per page
        offset = (page - 1) * per_page  # Offset for pagination

        # Base query
        query = "SELECT room_id, room_number, room_type, capacity, per_day, per_week, per_month, status FROM room WHERE 1=1"
        values = []

        # Apply filters dynamically
        if room_id:
            query += " AND room_id = %s"
            values.append(room_id)
        if room_number:
            query += " AND room_number = %s"
            values.append(room_number)
        if room_type:
            query += " AND room_type = %s"
            values.append(room_type)
        if capacity:
            query += " AND capacity = %s"
            values.append(capacity)
        if per_day:
            query += " AND per_day = %s"
            values.append(per_day)
        if per_week:
            query += " AND per_week = %s"
            values.append(per_week)
        if per_month:
            query += " AND per_month = %s"
            values.append(per_month)
        if status:
            query += " AND status = %s"
            values.append(status)

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        values.append(per_page)
        values.append(offset)

        # Execute query
        cur = mysql.connection.cursor()
        cur.execute(query, values)
        rooms = cur.fetchall()

        # Count total records (for pagination info)
        count_query = "SELECT COUNT(*) FROM room WHERE 1=1"
        cur.execute(count_query)
        total_records = cur.fetchone()[0]

        cur.close()  # Close cursor

        # Convert data into a list of dictionaries
        room_list = [
            {
                'room_id': room[0],
                'room_number': room[1],
                'room_type': room[2],
                'capacity': room[3],
                'per_day': room[4],
                'per_week': room[5],
                'per_month': room[6],
                'status': room[7]
            }
            for room in rooms
        ]

        # Calculate total pages
        total_pages = (total_records + per_page - 1) // per_page  # Equivalent to ceil(total_records / per_page)

        # Return JSON response with pagination metadata
        return jsonify({
            'data': room_list,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500








# Function to validate email format
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Function to validate if the category is valid
def is_valid_category(category):
    valid_categories = ['General', 'Service', 'Maintenance', 'Billing', 'Other']
    return category in valid_categories

@app.route('/api/register_complaint', methods=['POST'])
def register_complaint():
    data = request.get_json()

    # Extract data from the request
    name = data.get('name')
    email = data.get('email')
    subject = data.get('subject')
    category = data.get('category')
    message = data.get('message')

    # Validation checks
    if not name or not email or not subject or not category or not message:
        return jsonify({"error": "Missing required fields."}), 400

    if not is_valid_email(email):
        return jsonify({"error": "Invalid email format."}), 400

    if not is_valid_category(category):
        return jsonify({"error": "Invalid category. Valid options: 'General', 'Service', 'Maintenance', 'Billing', 'Other'."}), 400

    if len(message) < 10:
        return jsonify({"error": "Message should be at least 10 characters long."}), 400

    # Connect to the database and insert the complaint
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO complaints (name, email, subject, category, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, subject, category, message))

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Complaint submitted successfully!"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500






# Function to validate email format
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Function to validate feedback type (can be 'positive', 'neutral', or 'negative')
def is_valid_feedback_type(feedback_type):
    return feedback_type in ['positive', 'neutral', 'negative']

# Route to submit feedback with validation
@app.route('/api/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        # Ensure request contains JSON data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        # Extract data
        feedback_type = data.get('feedback_type')
        feedback_message = data.get('feedback_message')
        email = data.get('email')

        # Ensure all required fields are provided
        if not feedback_type or not feedback_message or not email:
            return jsonify({'error': 'All fields are required'}), 400

        # Validate feedback type
        if not is_valid_feedback_type(feedback_type):
            return jsonify({'error': "Invalid feedback type. Must be 'positive', 'neutral', or 'negative'."}), 400

        # Validate feedback message length (at least 10 characters)
        if len(feedback_message) < 10:
            return jsonify({'error': 'Feedback message must be at least 10 characters long.'}), 400

        # Validate email format
        if not is_valid_email(email):
            return jsonify({'error': 'Invalid email format.'}), 400

        # Connect to the database
        cur = mysql.connection.cursor()

        # Insert feedback into the database (Let MySQL handle submitted_at timestamp)
        cur.execute("""
            INSERT INTO feedback (feedback_type, feedback_message, email)
            VALUES (%s, %s, %s)
        """, (feedback_type, feedback_message, email))

        mysql.connection.commit()  # Commit the transaction
        cur.close()  # Close cursor

        return jsonify({'message': 'Feedback submitted successfully!'}), 200

    except Exception as e:
        app.logger.error(f"Error occurred while submitting feedback: {e}")
        return jsonify({'error': 'Error submitting feedback. Please try again.'}), 500


    
    
    



 
# Function to validate email format
def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Function to validate contact number format (must be 10 digits)
def is_valid_contact_number(contact_number):
    return contact_number.isdigit() and len(contact_number) == 10

@app.route("/api/user_profiles", methods=["POST"])
def create_user_profile():
    try:
        data = request.get_json()
        print("Received data:", data)  # Debugging statement

        first_name = data.get("firstName")
        middle_name = data.get("middleName", None)  # Convert empty to NULL
        last_name = data.get("lastName")
        gender = data.get("gender").lower()  # Convert to lowercase
        contact_number = data.get("contactNumber")
        email = data.get("email")

        # Ensure required fields are not missing
        if not first_name or not last_name or not gender or not contact_number or not email:
            return jsonify({"error": "Missing required fields"}), 400

        # Validate gender values
        valid_genders = ["male", "female", "other"]
        if gender not in valid_genders:
            return jsonify({"error": "Invalid gender value. Must be 'male', 'female', or 'other'."}), 400

        # Validate contact number
        if not is_valid_contact_number(contact_number):
            return jsonify({"error": "Invalid contact number. Must be exactly 10 digits."}), 400

        # Validate email format
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email format."}), 400

        # Check if email already exists
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM user_profiles WHERE email = %s", (email,))
        existing_user = cur.fetchone()
        if existing_user:
            return jsonify({"error": "Email already exists!"}), 400

        # Insert into database (MySQL will handle `created_at`)
        cur.execute("""
            INSERT INTO user_profiles (first_name, middle_name, last_name, gender, contact_number, email)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (first_name, middle_name, last_name, gender, contact_number, email))

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Profile created successfully!"}), 201

    except Exception as e:
        print(f"Error: {e}")  # Print the exact error
        return jsonify({"error": "Error submitting profile data. Please try again."}), 500





    
    
if __name__ == '__main__':
    app.run(debug=True)
