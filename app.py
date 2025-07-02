from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import InputRequired
import requests
import pytz
from datetime import datetime, timedelta
import os

app = Flask(__name__)

from dotenv import load_dotenv
load_dotenv()  

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['OPENWEATHERMAP_API_KEY'] = os.getenv('OPENWEATHERMAP_API_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#Forms
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

#User
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    preferred_city = db.Column(db.String(100))
    units = db.Column(db.String(10), default='metric')
    theme = db.Column(db.String(10), default='light')

# Routes
@app.route('/')
def home():
    try:
        url = f"https://newsapi.org/v2/everything?q=weather&from={(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}&sortBy=popularity&apiKey={app.config['NEWSAPI_KEY']}"
        news_data = requests.get(url).json().get('articles', [])[:3]
    except:
        news_data = []
    return render_template('home.html', news=news_data)

@app.route('/map')
def weather_map():
    return render_template('map.html', 
        api_key=app.config['OPENWEATHERMAP_API_KEY'])

@app.route('/alerts')
def weather_alerts():
    location = request.args.get('location', current_user.preferred_city if current_user.is_authenticated else None)
    
    if location:
        try:
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={app.config['OPENWEATHERMAP_API_KEY']}"
            geo_data = requests.get(geo_url).json()
            
            if geo_data:
                lat, lon = geo_data[0]['lat'], geo_data[0]['lon']
                alerts_url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=minutely,hourly&appid={app.config['OPENWEATHERMAP_API_KEY']}"
                weather_data = requests.get(alerts_url).json()
                
                processed_alerts = []
                for alert in weather_data.get('alerts', []):
                    processed_alerts.append({
                        'event': alert['event'],
                        'description': alert['description'],
                        'start': datetime.fromtimestamp(alert['start'], pytz.utc).strftime('%b %d, %H:%M'),
                        'end': datetime.fromtimestamp(alert['end'], pytz.utc).strftime('%b %d, %H:%M'),
                        'severity': alert.get('tags', ['Moderate'])[0]
                    })
                return render_template('alerts.html', alerts=processed_alerts, location=location)
        except Exception as e:
            flash(f"Couldn't fetch alerts: {str(e)}")
    
    return render_template('alerts.html', alerts=[], location=location)

@app.route('/weather', methods=['GET', 'POST'])
def weather():
    form = WeatherForm()
    weather_data = None
    
    if form.validate_on_submit():
        params = {
            'q': form.city.data,
            'appid': app.config['OPENWEATHERMAP_API_KEY'],
            'units': 'metric'
        }
        response = requests.get("http://api.openweathermap.org/data/2.5/weather", params=params)
        
        if response.status_code == 200:
            weather_data = response.json()
            weather_data['sys']['sunrise'] = datetime.fromtimestamp(weather_data['sys']['sunrise']).strftime('%H:%M')
            weather_data['sys']['sunset'] = datetime.fromtimestamp(weather_data['sys']['sunset']).strftime('%H:%M')
            weather_data['recommendations'] = get_clothing_recommendation(weather_data)
        else:
            flash('City not found. Please try again.')
    
    return render_template('weather.html', form=form, weather=weather_data)

@app.route('/forecast', methods=['GET', 'POST'])
def forecast():
    form = WeatherForm()
    forecast_data = None
    
    if form.validate_on_submit():
        params = {
            'q': form.city.data,
            'appid': app.config['OPENWEATHERMAP_API_KEY'],
            'units': 'metric',
            'cnt': 40
        }
        response = requests.get("http://api.openweathermap.org/data/2.5/forecast", params=params)
        
        if response.status_code == 200:
            forecast_data = process_forecast(response.json())
        else:
            flash('City not found. Please try again.')
    
    return render_template('forecast.html', form=form, forecast=forecast_data)

# Functions
def process_forecast(data):
    daily_data = {}
    for item in data['list']:
        date = item['dt_txt'].split()[0]
        if date not in daily_data:
            daily_data[date] = {
                'temps': [],
                'weather': [],
                'date': datetime.strptime(date, '%Y-%m-%d').strftime('%A, %b %d')
            }
        daily_data[date]['temps'].append(item['main']['temp'])
        daily_data[date]['weather'].append(item['weather'][0])
    
    return [{
        'date': values['date'],
        'avg_temp': round(sum(values['temps']) / len(values['temps']), 1),
        'icon': get_weather_icon(values['weather'][0]['id']),
        'description': values['weather'][0]['description']
    } for date, values in daily_data.items()][:5]

def get_clothing_recommendation(weather_data):
    temp = weather_data['main']['temp']
    conditions = weather_data['weather'][0]['main'].lower()
    recommendations = []
    
    if temp < 0: recommendations.append("Heavy winter coat, gloves, scarf, and hat")
    elif temp < 10: recommendations.append("Warm jacket and layers")
    elif temp < 20: recommendations.append("Light jacket or sweater")
    else: recommendations.append("Light clothing")
    
    if 'rain' in conditions: recommendations.append("Waterproof shoes and umbrella")
    if 'snow' in conditions: recommendations.append("Snow boots and thermal layers")
    if weather_data['main']['humidity'] > 80: recommendations.append("Breathable fabrics recommended")
    
    if 'uvi' in weather_data:
        uv = weather_data['uvi']
        if uv > 8: recommendations.append("SPF 50+ sunscreen essential")
        elif uv > 5: recommendations.append("SPF 30+ sunscreen recommended")
    
    return recommendations

def get_weather_icon(weather_id):
    if 200 <= weather_id <= 232: return 'wi-thunderstorm'
    elif 300 <= weather_id <= 321: return 'wi-sprinkle'
    elif 500 <= weather_id <= 531: return 'wi-rain'
    elif 600 <= weather_id <= 622: return 'wi-snow'
    elif 701 <= weather_id <= 781: return 'wi-fog'
    elif weather_id == 800: return 'wi-day-sunny'
    elif 801 <= weather_id <= 804: return 'wi-cloudy'
    return 'wi-day-cloudy'

# Core App Functions
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            password=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

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
    return render_template('preferences.html', form=form)

@app.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    current_user.theme = request.json['theme']
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/news')
def news():
    try:
        url = f"https://newsapi.org/v2/everything?q=weather&from={(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}&sortBy=popularity&apiKey={app.config['NEWSAPI_KEY']}"
        news_data = requests.get(url).json().get('articles', [])[:5]
    except:
        news_data = []
    return render_template('news.html', news=news_data)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_config():
    return {
        'config': {
            'OPENWEATHERMAP_API_KEY': app.config['OPENWEATHERMAP_API_KEY']
        }
    }
@app.context_processor
def utility_processor():
    return dict(get_weather_icon=get_weather_icon)

#  Initialization
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)