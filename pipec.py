from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import calendar
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = '12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///steps.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    steps = db.relationship('StepRecord', backref='user', lazy=True)

class StepRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    steps = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='unique_user_date'),)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_week_dates(year, week):
    first_day = datetime.strptime(f'{year}-{week}-1', '%Y-%W-%w')
    return [first_day + timedelta(days=i) for i in range(7)]

def get_month_dates(year, month):
    _, num_days = calendar.monthrange(year, month)
    return [date(year, month, day) for day in range(1, num_days + 1)]

def get_quarter_dates(year, quarter):
    start_month = (quarter - 1) * 3 + 1
    dates = []
    for month in range(start_month, start_month + 3):
        _, num_days = calendar.monthrange(year, month)
        dates.extend([date(year, month, day) for day in range(1, num_days + 1)])
    return dates

def get_year_dates(year):
    dates = []
    for month in range(1, 13):
        _, num_days = calendar.monthrange(year, month)
        dates.extend([date(year, month, day) for day in range(1, num_days + 1)])
    return dates

def calculate_average(steps_data, dates):
    total_steps = sum(steps_data.get(d, 0) for d in dates)
    return round(total_steps / len(dates), 2) if dates else 0

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('есть такой еблан уже')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('да есть такой ебанарот ')
            return render_template('register.html')
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('submit_steps'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('submit_steps'))
        else:
            flash('Че то ты проебал')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/submit_steps', methods=['GET', 'POST'])
@login_required
def submit_steps():
    if request.method == 'POST':
        steps = request.form.get('steps')
        record_date = request.form.get('date') or date.today().isoformat()
        
        if steps and steps.isdigit():
            try:
                record_date_obj = datetime.strptime(record_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format')
                return render_template('submit_steps.html')
            
            existing_record = StepRecord.query.filter_by(
                user_id=current_user.id, 
                date=record_date_obj
            ).first()
            
            if existing_record:
                existing_record.steps = int(steps)
            else:
                new_record = StepRecord(
                    user_id=current_user.id,
                    steps=int(steps),
                    date=record_date_obj
                )
                db.session.add(new_record)
            
            db.session.commit()
            flash('Steps submitted successfully!')
        else:
            flash('Please enter a valid number of steps')
    
    return render_template('submit_steps.html')

@app.route('/me')
@login_required
def user_profile():
    today = date.today()
    today_steps = StepRecord.query.filter_by(
        user_id=current_user.id, 
        date=today
    ).first()
    
    return render_template('profile.html', 
                         today_steps=today_steps.steps if today_steps else 0)

@app.route('/me/week')
@login_required
def current_week():
    today = date.today()
    year, week = today.isocalendar()[0], today.isocalendar()[1]
    return week_stats(year, week)

@app.route('/me/week/<int:week_num>')
@login_required
def week_n(week_num):
    year = date.today().year
    return week_stats(year, week_num)

def week_stats(year, week):
    week_dates = get_week_dates(year, week)
    steps_data = {}
    
    for record in StepRecord.query.filter_by(user_id=current_user.id).all():
        steps_data[record.date] = record.steps
    
    average = calculate_average(steps_data, week_dates)
    
    return jsonify({
        'period': 'week',
        'year': year,
        'week': week,
        'average_steps': average,
        'dates': [d.isoformat() for d in week_dates]
    })

@app.route('/me/month')
@login_required
def current_month():
    today = date.today()
    return month_stats(today.year, today.month)

@app.route('/me/month/<int:month_num>')
@login_required
def month_n(month_num):
    year = date.today().year
    return month_stats(year, month_num)

def month_stats(year, month):
    month_dates = get_month_dates(year, month)
    steps_data = {}
    
    for record in StepRecord.query.filter_by(user_id=current_user.id).all():
        steps_data[record.date] = record.steps
    
    average = calculate_average(steps_data, month_dates)
    
    return jsonify({
        'period': 'month',
        'year': year,
        'month': month,
        'average_steps': average,
        'dates': [d.isoformat() for d in month_dates]
    })

@app.route('/me/quarter')
@login_required
def current_quarter():
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    return quarter_stats(today.year, quarter)

@app.route('/me/quarter/<int:quarter_num>')
@login_required
def quarter_n(quarter_num):
    year = date.today().year
    return quarter_stats(year, quarter_num)

def quarter_stats(year, quarter):
    quarter_dates = get_quarter_dates(year, quarter)
    steps_data = {}
    
    for record in StepRecord.query.filter_by(user_id=current_user.id).all():
        steps_data[record.date] = record.steps
    
    average = calculate_average(steps_data, quarter_dates)
    
    return jsonify({
        'period': 'quarter',
        'year': year,
        'quarter': quarter,
        'average_steps': average,
        'dates': [d.isoformat() for d in quarter_dates]
    })

@app.route('/me/year')
@login_required
def current_year():
    year = date.today().year
    return year_stats(year)

@app.route('/me/year/<int:year_num>')
@login_required
def year_n(year_num):
    return year_stats(year_num)

def year_stats(year):
    year_dates = get_year_dates(year)
    steps_data = {}
    
    for record in StepRecord.query.filter_by(user_id=current_user.id).all():
        steps_data[record.date] = record.steps
    
    average = calculate_average(steps_data, year_dates)
    
    return jsonify({
        'period': 'year',
        'year': year,
        'average_steps': average,
        'dates': [d.isoformat() for d in year_dates]
    })


@app.route('/admin/users')          #админ панель
@login_required
def admin_users():
    
    if current_user.username != 'admin':  
        flash('Access denied')
        return redirect(url_for('submit_steps'))
    
    users = User.query.all()
    users_data = []
    
    for user in users:
        
        week_ago = date.today() - timedelta(days=7)
        recent_steps = StepRecord.query.filter(
            StepRecord.user_id == user.id,
            StepRecord.date >= week_ago
        ).all()
        
        total_recent_steps = sum(record.steps for record in recent_steps)
        
        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'password_hash': user.password_hash,
            'total_steps_week': total_recent_steps,
            'records_count': len(recent_steps)
        })
    
    return render_template('admin_users.html', users=users_data)

@app.route('/admin/stats')
@login_required
def admin_stats():
    if current_user.username != 'admin':
        flash('Access denied')
        return redirect(url_for('submit_steps'))
    
    
    total_users = User.query.count()
    total_step_records = StepRecord.query.count()
    
    
    week_ago = date.today() - timedelta(days=7)
    
    user_stats = []
    users = User.query.all()
    
    for user in users:
        recent_steps = StepRecord.query.filter(
            StepRecord.user_id == user.id,
            StepRecord.date >= week_ago
        ).all()
        
        total_steps = sum(record.steps for record in recent_steps)
        avg_steps = total_steps / len(recent_steps) if recent_steps else 0
        
        user_stats.append({
            'username': user.username,
            'total_steps': total_steps,
            'avg_steps': round(avg_steps, 2),
            'days_active': len(recent_steps)
        })
    
    
    user_stats.sort(key=lambda x: x['total_steps'], reverse=True)
    
    return render_template('admin_stats.html', 
                         total_users=total_users,
                         total_step_records=total_step_records,
                         user_stats=user_stats)


@app.route('/admin/user/<int:user_id>')
@login_required
def admin_user_detail(user_id):
    if current_user.username != 'admin':
        flash('Access denied')
        return redirect(url_for('submit_steps'))
    
    user = User.query.get_or_404(user_id)
    step_records = StepRecord.query.filter_by(user_id=user_id).order_by(StepRecord.date.desc()).all()
    
    return render_template('admin_user_detail.html', user=user, step_records=step_records)


@app.route('/create_admin')
def create_admin():
    
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(admin_user)
        db.session.commit()
        return 'Admin user created: username=admin, password=admin123'
    else:
        return 'Admin user already exists'





if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)



    
