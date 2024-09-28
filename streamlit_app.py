import streamlit as st
import sqlitecloud
import pandas as pd
import pytz
from datetime import datetime

# Initialize session state variables for progress tracking
if 'daily_annotated' not in st.session_state:
    st.session_state.daily_annotated = 0
if 'total_annotated' not in st.session_state:
    st.session_state.total_annotated = 0

# # Define target goals
# DAILY_TARGET = 60
# TOTAL_TARGET = 5000


# Initialize session state variables for history, current index, and flag
if 'history' not in st.session_state:
    st.session_state.history = []
if 'current_row_index' not in st.session_state:
    st.session_state.current_row_index = 0
if 'show_warning' not in st.session_state:
    st.session_state.show_warning = False

# Predefined list of valid annotator IDs
first = st.secrets["Annotatorid"]["first"]
second = st.secrets["Annotatorid"]["second"]
third = st.secrets["Annotatorid"]["third"]
forth = st.secrets["Annotatorid"]["forth"]
fifth = st.secrets["Annotatorid"]["fifth"]
valid_annotator_ids = [first, second, third, forth, fifth]

# Capture annotator ID at the start and store it in session state
if 'annotator_id' not in st.session_state:
    st.session_state.annotator_id = None

# Create a text input for the annotator ID
annotator_id_input = st.text_input("أدخل معرف المراجع (Annotator ID):")

# Update the session state once the annotator ID is entered
if annotator_id_input:
    st.session_state.annotator_id = annotator_id_input


# Set different DAILY_TARGET based on annotator_id
if st.session_state.annotator_id == first or st.session_state.annotator_id == third:
    DAILY_TARGET = 60  # Assign 100 for first and second annotators
    WORK_DAYS = 42 
    TOTAL_TARGET = DAILY_TARGET * WORK_DAYS
    start_date_str = "2024-09-24" 
elif st.session_state.annotator_id == second or st.session_state.annotator_id == forth or st.session_state.annotator_id == fifth:
    DAILY_TARGET = 60  # Assign 100 for first and second annotators
    WORK_DAYS = 42 
    TOTAL_TARGET = DAILY_TARGET * WORK_DAYS
    start_date_str = "2024-09-27" 
else:
    DAILY_TARGET = 10  # Assign 100 for first and second annotators
    WORK_DAYS = 40 
    TOTAL_TARGET = DAILY_TARGET * WORK_DAYS
    start_date_str = "2024-09-23" 
    st.error("معرف المراجع غير صحيح. يرجى إدخال معرف صالح.")
    st.stop()  # Stop execution until a valid ID is provided

# Set the start date for the 30-day task
# start_date_str = "2024-09-15"  # Set your desired start date in 'YYYY-MM-DD' format
start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

# Get the current date in user's timezone
current_date = datetime.now(pytz.timezone('Asia/Riyadh')).date()

# Calculate how many days have passed since the start date
# days_passed = (current_date - start_date).days
days_passed = max(0, (current_date - start_date).days)


# Recalculate expected progress based on days passed and set targets
expected_annotations = min(days_passed * DAILY_TARGET, TOTAL_TARGET)
# expected_annotations_yesterday = min((days_passed - 1) * DAILY_TARGET, TOTAL_TARGET)
expected_annotations_yesterday = min(max(days_passed - 1, 0) * DAILY_TARGET, TOTAL_TARGET)



# Initialize a list to store token mappings if not already done
if 'token_mappings' not in st.session_state:
    st.session_state.token_mappings = []


# Function to get the current time in the user's timezone
def get_local_time():
    user_timezone = pytz.timezone('Asia/Riyadh')
    local_time = datetime.now(user_timezone)
    return local_time.strftime('%Y-%m-%d %H:%M:%S')  # Format the timestamp



# Function to establish a fresh database connection
def get_db_connection():
    db_connect = st.secrets["dbcloud"]["db_connect"]
    db_name = st.secrets["dbcloud"]["db_name"]
    conn = sqlitecloud.connect(db_connect)
    conn.execute(f"USE DATABASE {db_name}")
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn

# Function to fetch rows that are unprocessed or skipped, and not taken or taken by the current annotator
def get_available_row():
    conn = get_db_connection()
    c = conn.cursor()
    annotator_id = st.session_state.annotator_id
    
    # Get list of skipped rows to exclude from fetching
    skipped_rows = st.session_state.get('skipped_rows', [])
    skipped_rows_placeholder = ','.join(['?'] * len(skipped_rows))

    # First, try to get a row that is already taken by this annotator
    if skipped_rows:
        c.execute(f'''
            SELECT * FROM original_data 
            WHERE (processed = "no" OR processed = "skipped")
            AND taken = "yes" 
            AND taken_by = ?
            AND entity_id NOT IN ({skipped_rows_placeholder})
            LIMIT 1
        ''', (annotator_id, *skipped_rows))
    else:
        c.execute('''
            SELECT * FROM original_data 
            WHERE (processed = "no" OR processed = "skipped")
            AND taken = "yes" 
            AND taken_by = ?
            LIMIT 1
        ''', (annotator_id,))
    
    row = c.fetchone()
    
    # If no such row exists, get a new available row that is either not taken or has a null annotator
    if not row:
        if skipped_rows:
            c.execute(f'''
                SELECT * FROM original_data 
                WHERE processed = "no"
                AND (taken = "no" OR (taken = "yes" AND taken_by IS NULL))
                AND entity_id NOT IN ({skipped_rows_placeholder})
                LIMIT 1
            ''', (*skipped_rows,))
        else:
            c.execute('''
                SELECT * FROM original_data 
                WHERE processed = "no"
                AND (taken = "no" OR (taken = "yes" AND taken_by IS NULL))
                LIMIT 1
            ''')
        row = c.fetchone()
        
        # If a new row is fetched, mark it as taken by the current annotator
        if row and row[7] == "no":  # Ensure 'taken' is 'no' before reserving
            entity_id = row[0]
            c.execute('''
                UPDATE original_data 
                SET taken = "yes", taken_by = ? 
                WHERE entity_id = ?
            ''', (annotator_id, entity_id))
            conn.commit()
    
    conn.close()
    return row





# Function to fetch rows based on the processed state
def get_rows_by_processed(processed_status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM original_data WHERE processed = ?', (processed_status,))
    rows = c.fetchall()
    conn.close()  # Close the connection after fetching rows
    return rows

# Function to update the original_data table based on action
def update_original_data(entity_id, action):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE original_data SET processed = ? WHERE entity_id = ?', (action, entity_id))
    conn.commit()
    conn.close()  # Close the connection after updating

# Function to save the annotation with the annotator ID and localized datestamp
def save_annotation(entity_id, selected_translation, edited_source, edited_translation, action):
    annotator_id = st.session_state.annotator_id  # Retrieve annotator ID from session state
    conn = get_db_connection()
    c = conn.cursor()

    # Get the current timestamp in the user's timezone
    local_timestamp = get_local_time()

    # Insert the annotation with the local timestamp
    c.execute('''
        INSERT INTO annotation (entity_id, selected_translation, edited_source, edited_translation, action, annotator_id, datestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (entity_id, selected_translation, edited_source, edited_translation, action, annotator_id, local_timestamp))

    conn.commit()
    conn.close()  # Close the connection after saving

    # Update progress
    st.session_state.daily_annotated += 1
    st.session_state.total_annotated += 1

# Function to fetch today's annotations based on datestamp and annotator_id
def get_daily_annotations():
    today = datetime.now(pytz.timezone('Asia/Riyadh')).strftime('%Y-%m-%d')  # Get today's date
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM annotation WHERE annotator_id = ? AND datestamp LIKE ?', 
              (st.session_state.annotator_id, f'{today}%'))
    count = c.fetchone()[0]
    conn.close()
    return count

# Function to fetch total annotations for the specific annotator
def get_total_annotations():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM annotation WHERE annotator_id = ?', 
              (st.session_state.annotator_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


# Function to tokenize text into words (simple whitespace tokenization)
def tokenize(text):
    return text.split()

# Function to save token mappings into the database
def save_token_mapping(entity_id, annotator_id, source_token, translation_token):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO token_mappings (entity_id, annotator_id, source_token, translation_token)
        VALUES (?, ?, ?, ?)
    ''', (entity_id, annotator_id, source_token, translation_token))
    conn.commit()
    conn.close()  # Close the connection after saving


# Function to display token mapping dropdowns and append the results to the list
def display_token_mapping(source_text, translation_text, entity_id):
    # Tokenize the source and translation texts
    source_tokens = tokenize(source_text)
    translation_tokens = tokenize(translation_text)
    
    st.markdown("""
    <p style='font-size:14px; color:gray;'>ملاحظة: إذا أردت اختيار كلمتين وليست كلمة واحدة فاضف علامة _ بين الكلمتين, على سبيل المثال: كيف_حالك</p>
    """, unsafe_allow_html=True)
    
    # Display dropdowns for selecting tokens
    selected_source_token = st.selectbox("اختر كلمة من النص الأصلي:", source_tokens)
    
    # **NEW FEATURE**: Show previously entered mappings for the selected source token
    if selected_source_token:
        # Normalize the token for comparison
        normalized_source_token = selected_source_token.strip()

        # # Debugging output
        # st.write(f"Selected Source Token: '{normalized_source_token}'")

        # Fetch existing mappings for the selected source token
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            SELECT source_token, translation_token, entity_id
            FROM token_mappings 
            WHERE source_token = ?
        ''', (normalized_source_token,))
        previous_mappings = c.fetchall()
        conn.close()
        
        # Display the count of previous mappings
        if previous_mappings:
            st.write(f"{len(previous_mappings)} ارتباطات سابقة لهذه الكلمة كالتالي:")

            # Fetching edited_source for each mapping
            conn = get_db_connection()
            c = conn.cursor()
            for mapping in previous_mappings:
                # Debugging: print the entity_id
                # st.write(f"Debug: entity_id={mapping[2]}")

                # Retrieve the edited_source from the annotation table based on entity_id
                c.execute('''
                    SELECT edited_source 
                    FROM annotation 
                    WHERE entity_id = ?
                ''', (mapping[2],))
                
                result = c.fetchone()

                edited_sources = result[0] if result else "غير متوفر" 
                # edited_source_display = ", ".join(edited_sources) if edited_sources else "غير متوفر"
                
                # Display the mapping with edited_source
                st.write(f"{mapping[0]} -> {mapping[1]}  :: {edited_sources}")
            conn.close()
        else:
            st.write("لا توجد ارتباطات سابقة لهذه الكلمة.")



    selected_translation_token = st.selectbox("اختر كلمة من الترجمة المختارة:", translation_tokens)

    # Button to temporarily store the selected token mappings in session state
    if st.button("تعيين ارتباط"):
        # Append the mapping to the list of token mappings in session state (temporary storage)
        st.session_state.token_mappings.append((entity_id, selected_source_token, selected_translation_token))

    # Display the list of all token mappings with an option to remove them
    if st.session_state.token_mappings:
        st.write("الارتباطات المؤقتة:")
        
        # Show all temporary mappings
        for mapping in st.session_state.token_mappings:
            st.write(f"{mapping[1]} -> {mapping[2]}")
        
        # Add a button to remove all temporary mappings
        if st.button("إزالة ارتباط"):
            # Clear all temporary mappings
            st.session_state.token_mappings = []






# Function to handle processing a row and then move to the next one
def process_row_callback():
    if not st.session_state.token_mappings:
        st.session_state.show_warning = True
        return
    else:
        st.session_state.show_warning = False

    row = st.session_state.current_row
    entity_id, _, _, translation_1, translation_2, translation_3, _, _, _, _ = row

    # Identify the selected translation
    if st.session_state.selected_translation == translation_1:
        selected_translation_key = "translation_1"
    elif st.session_state.selected_translation == translation_2:
        selected_translation_key = "translation_2"
    else:
        selected_translation_key = "translation_3"

    # Save the annotation with the selected translation
    save_annotation(entity_id, selected_translation_key, edited_source_text, edited_translation, "processed")
    update_original_data(entity_id, "yes")
    
    # Save all token mappings to the database at once when processing is confirmed
    for entity_id, source_token, translation_token in st.session_state.token_mappings:
        annotator_id = st.session_state.annotator_id
        save_token_mapping(entity_id, annotator_id, source_token, translation_token)
    
    # Clear the token mappings after processing
    st.session_state.token_mappings = []
    
    # Move to the next row after processing
    st.session_state.current_row = get_available_row()


# Function to handle rejecting a row
def reject_row_callback():
    row = st.session_state.current_row
    entity_id, _, _, translation_1, translation_2, translation_3, _, _, _, _ = row
    
    # Update the row status as rejected
    update_original_data(entity_id, "reject")
    
    # Clear the current row and fetch a new available one
    st.session_state.current_row = get_available_row()


# # Function to handle skipping a row (set processed to "no")
# def skip_row_callback():
#     row = st.session_state.current_row
#     entity_id, _, _, translation_1, translation_2, translation_3, _, _, _, _ = row
    
#     # Update the row status as not processed and clear the taken status
#     conn = get_db_connection()
#     c = conn.cursor()
#     c.execute('''
#         UPDATE original_data 
#         SET processed = "no", taken = "no", taken_by = NULL 
#         WHERE entity_id = ?
#     ''', (entity_id,))
#     conn.commit()
#     conn.close()
    
#     # Move to the next available row
#     st.session_state.current_row = get_available_row()


# Function to handle skipping a row (set processed to "skipped" and assign it to the current annotator)
def skip_row_callback():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get the current row information
    current_row = st.session_state.current_row
    entity_id = current_row[0]
    annotator_id = st.session_state.annotator_id
    
    # Update the row as "skipped" and assign it to the current annotator
    c.execute('''
        UPDATE original_data 
        SET processed = "skipped", taken = "yes", taken_by = ? 
        WHERE entity_id = ?
    ''', (annotator_id, entity_id))
    
    conn.commit()
    conn.close()
    
    # Add the entity_id to the list of skipped rows in session state
    if 'skipped_rows' not in st.session_state:
        st.session_state.skipped_rows = []
    st.session_state.skipped_rows.append(entity_id)
    
    # Fetch a new available row
    st.session_state.current_row = get_available_row()




# Fetch an available row if not already fetched
if 'current_row' not in st.session_state:
    st.session_state.current_row = get_available_row()

row = st.session_state.current_row

# Check if we have a row to process
if row:
    entity_id, keyword, source_text, translation_1, translation_2, translation_3, dialect, processed, taken, taken_by = row

    # RTL Styling for Arabic and button enhancement
    st.markdown("""
        <style>
        .stApp {
            direction: RTL;
            text-align: right;
        }
        .info-container {
            display: flex;
            justify-content: space-between;
            font-size: 18px;
            margin-bottom: 20px;
        }
        .stTextInput, .stRadio, .stTextArea {
            font-size: 18px;
        }
        .button-container {
            display: flex;
            justify-content: center;
            gap: 1px;
            margin-top: 20px;
        }
        .stButton button {
            width: 100px;
            height: 40px;
            font-size: 16px;
            border-radius: 8px;
        }
        .reject-button button {
            background-color: #FF4B4B;
            color: white;
            border: 1px solid #FF0000;
        }
        .skip-button button {
            background-color: #F1C40F;
            color: white;
            border: 1px solid #F39C12;
        }
        .process-button button {
            background-color: #2ECC71;
            color: white;
            border: 1px solid #27AE60;
        }
        h2, h3 {
            color: #F39C12;
        }
        </style>
        """, unsafe_allow_html=True)


    # Calculate today's and overall progress for the specific annotator
    st.session_state.daily_annotated = get_daily_annotations()
    st.session_state.total_annotated = get_total_annotations()

    # Progress feedback
    st.write(f"تمت مراجعة {st.session_state.daily_annotated} من أصل {DAILY_TARGET} اليوم")
    daily_progress = min(st.session_state.daily_annotated / DAILY_TARGET, 1.0)  # Ensure progress does not exceed 100%
    st.progress(daily_progress)

    if days_passed == 0:
        st.markdown(f"""
            <p><strong>مرحبا بك في اليوم الأول للترجمة</strong>. لقد بدأت اليوم وقمت بإدخال <span style="color:#F39C12;">{st.session_state.total_annotated}</span> جمل.</p>
        """, unsafe_allow_html=True)
    elif st.session_state.total_annotated >= expected_annotations:
        st.markdown(f"""
            <p><strong>عمل مميز</strong>.. مرّت <span style="color:#F39C12;">{days_passed}</span> أيام وقمت بإدخال <span style="color:#F39C12;">{st.session_state.total_annotated}</span> جمل.. بزيادة <span style="color:#F39C12;">{st.session_state.total_annotated - expected_annotations}</span> عن العدد المطلوب.</p>
        """, unsafe_allow_html=True)
    elif st.session_state.total_annotated < expected_annotations:
        st.markdown(f"""
            <p><strong>تحتاج إلى زيادة المعدل اليومي لتغطي</strong> <span style="color:#F39C12;">{expected_annotations - st.session_state.total_annotated}</span> المتأخرة بالإضافة إلى مهمة اليوم.. مرّت <span style="color:#F39C12;">{days_passed}</span> أيام وقمت بإدخال <span style="color:#F39C12;">{st.session_state.total_annotated}</span> جمل.</p>
        """, unsafe_allow_html=True)



    # Custom label and input for the source text
    st.markdown('<div class="custom-label" style="color:#F39C12; font-weight:bold;">الجملة العامية:</div>', unsafe_allow_html=True)
    edited_source_text = st.text_area("", value=source_text)

    # Custom label and input for the translation options
    st.markdown('<div class="custom-label" style="color:#F39C12; font-weight:bold;">اختر الترجمة:</div>', unsafe_allow_html=True)
    st.session_state.selected_translation = st.radio("", options=[translation_1, translation_2, translation_3], key=f"translation_{entity_id}")

    # Custom label and input for editing the selected translation
    st.markdown('<div class="custom-label" style="color:#F39C12; font-weight:bold;">تحرير الترجمة المختارة:</div>', unsafe_allow_html=True)
    edited_translation = st.text_area("", value=st.session_state.selected_translation)

    # Display token mapping interface directly below the selected translation
    display_token_mapping(edited_source_text, edited_translation, entity_id)
    
    # Check if we need to display the warning (show it just above the buttons)
    if st.session_state.get('show_warning', False):
        st.markdown('<div style="color: red; text-align: center;">يرجى تعيين ارتباط الكلمات قبل معالجة المدخل.</div>', unsafe_allow_html=True)


    # Buttons with better formatting for processing actions
    st.markdown('<div class="button-container">', unsafe_allow_html=True)
    
    # Align buttons in the same row
    col1, col2, col3 = st.columns([1, 1, 1])


        
    with col1:
        st.markdown('<div class="process-button">', unsafe_allow_html=True)
        st.button("معالجة", on_click=lambda: process_row_callback())
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="skip-button">', unsafe_allow_html=True)
        st.button("تخطي", on_click=lambda: skip_row_callback())
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="reject-button">', unsafe_allow_html=True)
        st.button("رفض", on_click=lambda: reject_row_callback())
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

else:
    st.write("لا توجد صفوف غير معالجة متاحة.")
