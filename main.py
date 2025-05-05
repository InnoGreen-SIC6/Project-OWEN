from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from pymongo import MongoClient
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)
app.secret_key = 'owen_sic2025'

# Konfigurasi MongoDB
MONGO_URI = "mongodb+srv://ESP32-INNOGREEN:samsungindonesia_bisa@esp32-innogreen.depxs.mongodb.net/?retryWrites=true&w=majority&appName=ESP32-INNOGREEN"
DB_NAME = 'ESP32-INNOGREEN'
COLLECTION_NAME = 'InnoGreen'
PREDICTION_COLLECTION = 'Predictions'

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]
prediction_collection = db[PREDICTION_COLLECTION]

USER_FILE = 'users.txt'

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Fungsi untuk memuat data pengguna dari file
def load_users():
    users_data = {}
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) == 3:
                        username, password, nama = parts
                        users_data[username] = {'password': password, 'nama': nama}
                    elif len(parts) == 2:  # handle the case where nama is not provided
                        username, password = parts
                        users_data[username] = {'password': password, 'nama': ''}  # set default nama
        except Exception as e:
            logger.error(f"Error loading users from file: {e}")
            return {}  # Return empty dict on error to avoid crashing
    return users_data

# Fungsi untuk menyimpan data pengguna ke file
def save_user(username, password, nama=None):
    if nama is None:
        nama = ""  # Default value for nama
    try:
        with open(USER_FILE, 'a') as f:
            f.write(f'{username}:{password}:{nama}\n')
    except Exception as e:
        logger.error(f"Error saving user to file: {e}")

# Fungsi untuk melatih model machine learning
def train_model():
    try:
        # Fetch all data from MongoDB
        data_mongo = list(collection.find())
        df = pd.DataFrame(data_mongo)
        if df.empty:
            logger.warning("No data available in MongoDB for training the model.")
            return None, None

        df.columns = df.columns.str.strip()

        # Define ideal ranges (ini perlu disesuaikan berdasarkan pengetahuan domain Anda)
        df['suhu_ideal'] = ((df['suhu'] >= 25) & (df['suhu'] <= 30)).astype(int)
        df['kelembaban_ideal'] = ((df['kelembaban'] >= 60) & (df['kelembaban'] <= 80)).astype(int)
        df['kekeruhan_ideal'] = (df['turbidity'] <= 5).astype(int)
        df['ph_ideal'] = ((df['ph'] >= 6.5) & (df['ph'] <= 7.5)).astype(int)

        # Target variable: apakah semua kondisi ideal terpenuhi
        df['kondisi_ideal'] = df['suhu_ideal'] & df['kelembaban_ideal'] & df['kekeruhan_ideal'] & df['ph_ideal']

        # Features
        X = df[['suhu', 'kelembaban', 'turbidity', 'ph']]
        y = df['kondisi_ideal']

        if len(df) < 2:  # Memastikan ada cukup data untuk di split
            logger.warning("Insufficient data for training the model. Need at least 2 data points.")
            return None, None

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        logger.info(f"Model trained successfully with accuracy: {accuracy:.2f}")
        return model, X.columns
    except Exception as e:
        logger.error(f"Error training the model: {e}")
        return None, None

model, feature_columns = train_model()

def predict_and_analyze(data):
    if model is None or feature_columns is None:
        return None, {"status": "error", "message": "Model belum dilatih karena kekurangan data."}
    try:
        input_df = pd.DataFrame([data], columns=feature_columns)
        prediction = model.predict(input_df)[0]
        analysis = {}
        if prediction == 0:
            analysis['status'] = 'tidak ideal'
            reasons = []
            if data.get('suhu') is not None and not (25 <= data['suhu'] <= 30):
                reasons.append(f"Suhu tidak ideal ({data['suhu']}°C)")
            if data.get('kelembaban') is not None and not (60 <= data['kelembaban'] <= 80):
                reasons.append(f"Kelembaban tidak ideal ({data['kelembaban']}%)")
            if data.get('turbidity') is not None and not (data['turbidity'] <= 5):
                reasons.append(f"Kekeruhan terlalu tinggi ({data['turbidity']} %)")
            if data.get('ph') is not None and not (6.5 <= data['ph'] <= 7.5):
                reasons.append(f"pH tidak ideal ({data['ph']})")
            analysis['reasons'] = reasons
        else:
            analysis['status'] = 'ideal'
            analysis['reasons'] = []
        return prediction, analysis
    except Exception as e:
        logger.error(f"Error during prediction and analysis: {e}")
        return None, {"status": "error", "message": f"Terjadi kesalahan dalam analisis: {e}"}

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('beranda'))
    return redirect(url_for('login'))

@app.route('/beranda')
def beranda():
    if 'email' in session:
        try:
            latest_data_db = collection.find_one(sort=[('_id', -1)])
            if latest_data_db:
                latest_data_db['_id'] = str(latest_data_db['_id'])
            return render_template('beranda.html', latest_data=latest_data_db)
        except Exception as e:
            logger.error(f"Error fetching latest data for beranda: {e}")
            return render_template('beranda.html', latest_data=None, error_message="Failed to retrieve latest data.")
    return redirect(url_for('login'))

@app.route('/menu')
def menu():
    if 'email' in session:
        return render_template('menu.html')
    return redirect(url_for('login'))

@app.route('/notif')
def notif():
    if 'email' in session:
        try:
            latest_prediction = prediction_collection.find({}, sort=[('_id', -1)]).limit(1)
            prediction_data = list(latest_prediction)
            if prediction_data:
                return render_template('notif.html', prediction=prediction_data[0])
            else:
                return render_template('notif.html', prediction=None, message="Belum ada notifikasi.")
        except Exception as e:
            logger.error(f"Error fetching prediction data for notif: {e}")
            return render_template('notif.html', prediction=None, error_message="Failed to retrieve notification data.")
    return redirect(url_for('login'))

@app.route('/all_predictions', methods=['GET'])
def get_all_predictions():
    if 'email' in session:
        try:
            all_predictions_data = list(prediction_collection.find({}))
            for prediction in all_predictions_data:
                prediction['_id'] = str(prediction['_id'])
            return jsonify(all_predictions_data)
        except Exception as e:
            logger.error(f"Error fetching all predictions: {e}")
            return jsonify({'message': f'Error fetching all predictions: {e}'}), 500
    return redirect(url_for('login'))

@app.route('/profil')
def profil():
    if 'email' in session:
        users = load_users()
        user_data = users.get(session['email'])
        return render_template('profile.html', user=user_data)
    return redirect(url_for('login'))

@app.route('/pasokan')
def pasokan():
    if 'email' in session:
        return render_template('pasokan.html')
    return redirect(url_for('login'))

@app.route('/kipas')
def kipas():
    if 'email' in session:
        return render_template('kipas.html')
    return redirect(url_for('login'))

@app.route('/pembuangan')
def pembuangan():
    if 'email' in session:
        return render_template('pembuangan.html')
    return redirect(url_for('login'))

@app.route('/sensor')
def sensor():
    if 'email' in session:
        return render_template('sensor.html')
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
def upload_data():
    data = request.get_json()
    if data:
        logger.info(f'Data diterima dari ESP32: {data}')
        try:
            # Simpan data mentah ke koleksi utama
            result = collection.insert_one(data)
            inserted_id = str(result.inserted_id)
            logger.info(f'Data saved to MongoDB with _id: {inserted_id}')

            # Lakukan prediksi
            prediction, analysis = predict_and_analyze(data)
            if prediction is not None:
                prediction_data = {
                    'timestamp': datetime.now(),
                    'suhu': data.get('suhu'),
                    'kelembaban': data.get('kelembaban'),
                    'turbidity': data.get('turbidity'),
                    'ph': data.get('ph'),
                    'kondisi': analysis['status'],
                    'reasons': analysis.get('reasons', [])
                }
                prediction_result = prediction_collection.insert_one(prediction_data)
                logger.info(f"Prediction saved to Predictions collection with _id: {str(prediction_result.inserted_id)}")

            global model, feature_columns
            return jsonify(
                {'status': 'success', 'message': 'Data saved and analyzed',
                 '_id': inserted_id, 'prediction': analysis})
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            return jsonify(
                {'status': 'failed', 'message': f'Error processing data: {e}'}), 500
    return jsonify({'status': 'failed', 'message': 'No data received'}), 400

@app.route('/latest_data', methods=['GET'])
def get_latest_data():
    try:
        latest_data = collection.find_one(sort=[('_id', -1)])
        if latest_data:
            latest_data['_id'] = str(latest_data['_id'])
            return jsonify(latest_data)
        return jsonify({'message': 'No data available'}), 404
    except Exception as e:
        logger.error(f"Error fetching latest data: {e}")
        return jsonify({'message': f'Error fetching data: {e}'}), 500

@app.route('/all_data', methods=['GET'])
def get_all_data():
    try:
        all_data = []
        for document in collection.find():
            document['_id'] = str(document['_id'])
            all_data.append(document)
        return jsonify(all_data)
    except Exception as e:
        logger.error(f"Error fetching all data: {e}")
        return jsonify({'message': f'Error fetching all data: {e}'}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nama = request.form['nama']
        email = request.form['email']
        password = request.form['password']
        users = load_users()
        if email in users:
            return render_template('daftar.html',
                                   error='Email sudah terdaftar')
        save_user(email, password, nama)
        return redirect(url_for('login'))
    return render_template('daftar.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        users = load_users()
        if email in users and users[email]['password'] == password:
            session['email'] = email
            return redirect(url_for('beranda'))
        return render_template('login.html',
                               error='Email atau password salah')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)