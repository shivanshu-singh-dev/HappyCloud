# Move all imports to top
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import InputRequired
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['OPENWEATHERMAP_API_KEY'] = '3f30720cc3d8946f6df8ab9a53d4179d'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Forms ---
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired()])
    password = PasswordField('Password', validators=[InputRequired()])

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[InputRequired()])
    password = PasswordField('Password', validators=[InputRequired()])

class WeatherForm(FlaskForm):
    city = StringField('City', validators=[InputRequired()])
    submit = SubmitField('Get Weather')

class PreferencesForm(FlaskForm):
    city = StringField('Default City')
    units = SelectField('Units', choices=[('metric', '°C'), ('imperial', '°F')])
    theme = SelectField('Theme', choices=[('light', 'Light'), ('dark', 'Dark')])
    submit = SubmitField('Save Preferences')

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    preferred_city = db.Column(db.String(100))
    units = db.Column(db.String(10), default='metric')
    theme = db.Column(db.String(10), default='light')

# --- Routes ---
@app.route('/')
def home():
    # Get news data directly for homepage
    news_api_key = "YOUR_NEWSAPI_KEY"
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    url = f"https://newsapi.org/v2/everything?q=weather&from={from_date}&sortBy=popularity&apiKey={news_api_key}"
    
    try:
        response = requests.get(url)
        news_data = response.json().get('articles', [])[:3]  # Just 3 for homepage
    except:
        news_data = []
    
    return render_template('home.html', news=news_data) 

@app.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    data = request.get_json()
    current_user.theme = data['theme']
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/news')
def news():
    news_api_key = "1738fff3200749e5b53bdc8205093f8d"  
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    url = f"https://newsapi.org/v2/everything?q=weather&from={from_date}&sortBy=popularity&apiKey={news_api_key}"
    
    try:
        response = requests.get(url)
        news_data = response.json().get('articles', [])[:5] 
    except:
        news_data = []
    
    return render_template('news.html', news=news_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(username=form.username.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/forecast', methods=['GET', 'POST'])
@login_required
def forecast():
    form = WeatherForm()  # Reuse the same form as current weather
    forecast_data = None
    
    if form.validate_on_submit():
        city = form.city.data
        api_key = app.config['OPENWEATHERMAP_API_KEY']
        base_url = "http://api.openweathermap.org/data/2.5/forecast"
        
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric',
            'cnt': 40  # Get 5 days of data (8 forecasts per day)
        }
        
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            forecast_data = process_forecast(response.json())
        else:
            flash('City not found. Please try again.')
    
    return render_template('forecast.html', form=form, forecast=forecast_data)

def process_forecast(data):
    """Group 3-hour forecasts into daily forecasts"""
    daily_data = {}
    for item in data['list']:
        date = item['dt_txt'].split()[0]  # Extract just the date
        if date not in daily_data:
            daily_data[date] = {
                'temps': [],
                'weather': [],
                'date': datetime.strptime(date, '%Y-%m-%d').strftime('%A, %b %d')
            }
        daily_data[date]['temps'].append(item['main']['temp'])
        daily_data[date]['weather'].append(item['weather'][0])
    
    # Calculate daily averages
    processed = []
    for date, values in daily_data.items():
        processed.append({
            'date': values['date'],
            'avg_temp': round(sum(values['temps']) / len(values['temps']), 1),
            'icon': get_weather_icon(values['weather'][0]['id']),  # Use first weather icon
            'description': values['weather'][0]['description']
        })
    
    return processed[:5]  # Return just 5 days

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid username or password')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/weather', methods=['GET', 'POST'])
@login_required
def weather():
    form = WeatherForm()
    weather_data = None
    
    if form.validate_on_submit():
        city = form.city.data
        api_key = app.config['OPENWEATHERMAP_API_KEY']
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric'
        }
        
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            weather_data = response.json()
            weather_data['sys']['sunrise'] = datetime.fromtimestamp(weather_data['sys']['sunrise']).strftime('%H:%M')
            weather_data['sys']['sunset'] = datetime.fromtimestamp(weather_data['sys']['sunset']).strftime('%H:%M')
        else:
            flash('City not found. Please try again.')
    
    return render_template('weather.html', form=form, weather=weather_data)

@app.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    form = PreferencesForm(obj=current_user)
    if form.validate_on_submit():
        current_user.preferred_city = form.city.data
        current_user.units = form.units.data
        current_user.theme = form.theme.data
        db.session.commit()
        flash('Preferences updated!')
        return redirect(url_for('preferences'))
    return render_template('preferences.html', form=form)

# --- Utility Functions ---
def get_weather_icon(weather_id):
    """Map OpenWeatherMap weather codes to weather icons"""
    if 200 <= weather_id <= 232: return 'wi-thunderstorm'
    elif 300 <= weather_id <= 321: return 'wi-sprinkle'
    elif 500 <= weather_id <= 531: return 'wi-rain'
    elif 600 <= weather_id <= 622: return 'wi-snow'
    elif 701 <= weather_id <= 781: return 'wi-fog'
    elif weather_id == 800: return 'wi-day-sunny'
    elif 801 <= weather_id <= 804: return 'wi-cloudy'
    return 'wi-day-cloudy'

@app.context_processor
def utility_processor():
    return dict(get_weather_icon=get_weather_icon)

# --- Initialization ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)