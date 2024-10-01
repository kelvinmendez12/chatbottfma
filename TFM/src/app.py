import requests
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from PyPDF2 import PdfReader
import pandas as pd
import re
import pyrebase
import os

# Configuración de Firebase
config = {
    'apiKey': os.getenv('API_KEY'),
    'authDomain': os.getenv('AUTH_DOMAIN'),
    'databaseURL': os.getenv('DATABASE_URL'),
    'projectId': os.getenv('PROJECT_ID'),
    'storageBucket': os.getenv('STORAGE_BUCKET'),
    'messagingSenderId': os.getenv('MESSAGING_SENDER_ID'),
    'appId': os.getenv('APP_ID'),
    'measurementId': os.getenv('MEASUREMENT_ID')
}

firebase_config = {
    "type": "service_account",
    "project_id": os.getenv('PROJECT_ID'),
    "private_key_id": os.getenv('PRIVATE_KEY_ID'),
    "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": os.getenv('FIREBASE_AUTH_URI'),
    "token_uri": os.getenv('FIREBASE_TOKEN_URI'),
    "auth_provider_x509_cert_url": os.getenv('FIREBASE_AUTH_PROVIDER_CERT_URL'),
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL'),
    "universe_domain": "googleapis.com"
}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')  # Usa una variable de entorno para la clave secreta

# Función para determinar el tipo de archivo
def get_file_type(file):
    return file.filename.rsplit('.', 1)[-1].lower()

# Función para crear embeddings
def create_embeddings(file, file_type):
    if file:
        if file_type == 'pdf':
            pdf_reader = PdfReader(file)
            text = "".join(page.extract_text() for page in pdf_reader.pages)
            if not text.strip():
                raise ValueError("No se pudo extraer texto del PDF.")
            chunks = text.split("\n\n")  # Cambia esto según tus necesidades
            return chunks

        elif file_type in ['xlsx', 'xls']:
            df = pd.read_excel(file)  # Leer el archivo de Excel
            text = df.to_string(index=False)  # Convertir el DataFrame a texto
            chunks = text.split("\n\n")  # Cambia esto según tus necesidades
            return chunks

        else:
            raise ValueError("Tipo de archivo no soportado.")

    raise ValueError("No se proporcionó ningún archivo.")

# Función para realizar la llamada a la API de OpenAI
def query_openai(prompt):
    openai_api_key = os.getenv('OPENAI_API_KEY')
    headers = {
        'Authorization': f'Bearer {openai_api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'gpt-4o',
        'messages': [{'role': 'user', 'content': prompt}]
    }
    response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data)
    if response.status_code == 200:
        answer = response.json()['choices'][0]['message']['content']

        # Formatear la respuesta
        formatted_answer = answer.replace("\n", "<br>")  # Reemplaza saltos de línea
        
        # Reemplazar títulos por negrita y eliminar los signos de ### (y cualquier otra marca que quieras quitar)
        formatted_answer = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted_answer)  # Títulos en negritas
        formatted_answer = re.sub(r'### (.+?)\n', r'<strong>\1</strong><br>', formatted_answer)  # Títulos en negritas
        formatted_answer = formatted_answer.replace('**', '')  # Eliminar asteriscos si hay

        return formatted_answer
    else:
        raise Exception(f"Error {response.status_code}: {response.text}")

# Ruta principal
@app.route('/')
@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['user_email']
        password = request.form['user_pwd']
        try:
            # Iniciar sesión del usuario
            user_info = auth.sign_in_with_email_and_password(email, password)
            session['user'] = user_info['localId']  # Guardar ID de usuario en la sesión
            return render_template('pdf_chatbot.html')  # Redirigir a la página del chatbot
        except Exception as e:
            print("Exception occurred:", e)
            unsuccessful = 'Por favor, verifica tus credenciales'
            return render_template('index.html', umessage=unsuccessful)
    return render_template('index.html')

# Ruta para el chatbot de PDF
@app.route('/pdf_chatbot', methods=['GET', 'POST'])
def pdf_chatbot():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user']

    if request.method == 'POST':
        file = request.files.get('pdf_file')  # Cambia a get para evitar KeyError
        query = request.form.get('query')  # Cambia a get para evitar KeyError
        
        if not file or not query:
            return jsonify({'error': 'Archivo o consulta faltante.'}), 400

        try:
            # Determinar el tipo de archivo
            file_type = get_file_type(file)
            # Crear embeddings
            chunks = create_embeddings(file, file_type)
            
            # Generar la respuesta usando el modelo de OpenAI
            prompt = f"Basado en la siguiente información: {', '.join(chunks)}. Responde a la pregunta: {query}"
            response = query_openai(prompt)

            return jsonify({'response': response})

        except Exception as e:
            print(f"Error occurred: {e}")  # Imprimir el error en la consola
            return jsonify({'error': str(e)}), 400  # Enviar el mensaje de error al cliente

    return render_template('pdf_chatbot.html')

# Ruta para crear una cuenta
@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        pwd0 = request.form['user_pwd0']
        pwd1 = request.form['user_pwd1']
        if pwd0 == pwd1:
            try:
                email = request.form['user_email']
                # Crear un nuevo usuario
                auth.create_user_with_email_and_password(email, pwd0)
                return render_template('index.html', umessage='Cuenta creada con éxito. Inicia sesión.')
            except Exception as e:
                return render_template('index.html', umessage=f'Error: {str(e)}')

    return render_template('create_account.html')

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.pop('user', None)  # Eliminar el ID de usuario de la sesión
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
