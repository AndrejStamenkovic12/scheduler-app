from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import json
import os
import hashlib
import base64
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
# Use a consistent secret key to prevent session loss on app restart
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-12345678')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size

# Session configuration for persistent login
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session lasts 7 days

# Simple authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Simple User Manager
class SimpleUserManager:
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self.users = self.load_users()
    
    def load_users(self):
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username, password, email="", 
                   role="consumer", **kwargs):
        if any(user['username'].lower() == username.lower() for user in self.users):
            return False
        
        user = {
            'id': len(self.users) + 1,
            'username': username,
            'password': self.hash_password(password),
            'email': email,
            'phone': kwargs.get('phone', ''),
            'name': kwargs.get('name', username),
            'profile_picture': '',
            'role': role,  # 'consumer' or 'provider'
            'created_at': datetime.now().isoformat()
        }
        
        # Provider-specific fields
        if role == 'provider':
            user['business_name'] = kwargs.get('business_name', '')
            user['business_description'] = kwargs.get('business_description', '')
            user['service_category'] = kwargs.get('service_category', '')
            user['services_offered'] = kwargs.get('services_offered', '')
            user['address'] = kwargs.get('address', '')
            user['availability'] = kwargs.get('availability', {
                'monday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                'tuesday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                'wednesday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                'thursday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                'friday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
                'saturday': {'enabled': False, 'start': '09:00', 'end': '17:00'},
                'sunday': {'enabled': False, 'start': '09:00', 'end': '17:00'}
            })
        
        self.users.append(user)
        self.save_users()
        return True
    
    def authenticate(self, username, password):
        user = next((u for u in self.users if u['username'].lower() == username.lower()), None)
        if user and user['password'] == self.hash_password(password):
            user_data = {
                'id': user['id'], 
                'username': user['username'], 
                'email': user.get('email', ''),
                'phone': user.get('phone', ''),
                'name': user.get('name', user['username']),
                'profile_picture': user.get('profile_picture', ''),
                'role': user.get('role', 'consumer')
            }
            
            # Add provider-specific fields
            if user.get('role') == 'provider':
                user_data['business_name'] = user.get('business_name', '')
                user_data['business_description'] = user.get('business_description', '')
                user_data['service_category'] = user.get('service_category', '')
                user_data['services_offered'] = user.get('services_offered', '')
                user_data['address'] = user.get('address', '')
                user_data['availability'] = user.get('availability', {})
            
            return user_data
        return None
    
    def get_user_by_id(self, user_id):
        user = next((u for u in self.users if u['id'] == user_id), None)
        if user:
            user_data = {
                'id': user['id'], 
                'username': user['username'], 
                'email': user.get('email', ''),
                'phone': user.get('phone', ''),
                'name': user.get('name', user['username']),
                'profile_picture': user.get('profile_picture', ''),
                'role': user.get('role', 'consumer')
            }
            
            # Add provider-specific fields
            if user.get('role') == 'provider':
                user_data['business_name'] = user.get('business_name', '')
                user_data['business_description'] = user.get('business_description', '')
                user_data['service_category'] = user.get('service_category', '')
                user_data['services_offered'] = user.get('services_offered', '')
                user_data['address'] = user.get('address', '')
                user_data['availability'] = user.get('availability', {})
                user_data['gallery'] = user.get('gallery', [])
            
            return user_data
        return None
    
    def update_user(self, user_id, name=None, email=None, 
                   phone=None, profile_picture=None, **kwargs):
        user = next((u for u in self.users if u['id'] == user_id), None)
        if not user:
            return False
        
        if name is not None:
            user['name'] = name
        if email is not None:
            user['email'] = email
        if phone is not None:
            user['phone'] = phone
        if profile_picture is not None:
            user['profile_picture'] = profile_picture
        
        # Provider-specific fields
        if user.get('role') == 'provider':
            if 'business_name' in kwargs:
                user['business_name'] = kwargs['business_name']
            if 'business_description' in kwargs:
                user['business_description'] = kwargs['business_description']
            if 'service_category' in kwargs:
                user['service_category'] = kwargs['service_category']
            if 'services_offered' in kwargs:
                user['services_offered'] = kwargs['services_offered']
            if 'address' in kwargs:
                user['address'] = kwargs['address']
        
        self.save_users()
        return True

# Initialize managers
user_manager = SimpleUserManager()


class AppointmentScheduler:
    def __init__(self, data_file: str = "appointments.json"):
        self.data_file = data_file
        self.appointments = self.load_appointments()
        self.appointment_types = {
            "hair": "Hair Salon",
            "nails": "Nail Salon", 
            "massage": "Massage Therapy",
            "training": "Personal Training",
            "spa": "Spa Treatment",
            "other": "Other"
        }
    
    def load_appointments(self):
        """Load appointments from JSON file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    for apt in data:
                        apt['datetime'] = datetime.fromisoformat(apt['datetime'])
                        apt['created_at'] = datetime.fromisoformat(apt['created_at'])
                    return data
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def save_appointments(self):
        """Save appointments to JSON file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.appointments, f, indent=2, default=str)
    
    def add_appointment(self, appointment_type, date, time, 
                       duration, notes="", user_id=None, 
                       provider_id=None):
        """Add a new appointment"""
        try:
            # Parse date and time
            appointment_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            
            # Check for conflicts
            if self.has_conflict(appointment_datetime, duration):
                return False
            
            appointment = {
                "id": len(self.appointments) + 1,
                "type": appointment_type,
                "datetime": appointment_datetime,
                "duration": duration,
                "notes": notes,
                "created_at": datetime.now(),
                "user_id": user_id,
                "provider_id": provider_id,
                "status": "pending"  # pending, confirmed, declined
            }
            
            self.appointments.append(appointment)
            self.save_appointments()
            return True
            
        except ValueError:
            return False
    
    def has_conflict(self, appointment_datetime, duration):
        """Check if appointment conflicts with existing ones"""
        end_time = appointment_datetime + timedelta(minutes=duration)
        
        for existing in self.appointments:
            existing_start = existing["datetime"]
            existing_end = existing_start + timedelta(minutes=existing["duration"])
            
            # Check for overlap
            if (appointment_datetime < existing_end and end_time > existing_start):
                return True
        return False
    
    def get_appointments(self, date=None):
        """Get appointments, optionally filtered by date"""
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
                return [apt for apt in self.appointments 
                       if apt["datetime"].date() == target_date]
            except ValueError:
                return []
        return sorted(self.appointments, key=lambda x: x["datetime"])
    
    def cancel_appointment(self, appointment_id):
        """Cancel an appointment by ID"""
        for i, appointment in enumerate(self.appointments):
            if appointment["id"] == appointment_id:
                del self.appointments[i]
                self.save_appointments()
                return True
        return False
    
    def get_appointment_types(self):
        """Get available appointment types"""
        return self.appointment_types

# Initialize scheduler
scheduler = AppointmentScheduler()


class ReviewManager:
    def __init__(self, reviews_file: str = "reviews.json"):
        self.reviews_file = reviews_file
        self.reviews = self.load_reviews()
    
    def load_reviews(self):
        """Load reviews from JSON file"""
        if os.path.exists(self.reviews_file):
            try:
                with open(self.reviews_file, 'r') as f:
                    data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    for review in data:
                        review['created_at'] = datetime.fromisoformat(review['created_at'])
                    return data
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def save_reviews(self):
        """Save reviews to JSON file"""
        with open(self.reviews_file, 'w') as f:
            json.dump(self.reviews, f, indent=2, default=str)
    
    def add_review(self, appointment_id, reviewer_id, reviewed_id, rating, comment=""):
        """Add a new review"""
        try:
            # Validate rating
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                return False
            
            # Check if review already exists for this appointment
            existing_review = next((r for r in self.reviews 
                                 if r['appointment_id'] == appointment_id and 
                                    r['reviewer_id'] == reviewer_id), None)
            if existing_review:
                return False
            
            review = {
                "id": len(self.reviews) + 1,
                "appointment_id": appointment_id,
                "reviewer_id": reviewer_id,
                "reviewed_id": reviewed_id,
                "rating": rating,
                "comment": comment.strip(),
                "created_at": datetime.now()
            }
            
            self.reviews.append(review)
            self.save_reviews()
            return True
            
        except Exception:
            return False
    
    def get_reviews_for_user(self, user_id):
        """Get all reviews for a specific user (reviews they received)"""
        return [review for review in self.reviews if review['reviewed_id'] == user_id]
    
    def get_reviews_by_user(self, user_id):
        """Get all reviews written by a specific user"""
        return [review for review in self.reviews if review['reviewer_id'] == user_id]
    
    def get_review_for_appointment(self, appointment_id, reviewer_id):
        """Get review for a specific appointment by a specific reviewer"""
        return next((r for r in self.reviews 
                    if r['appointment_id'] == appointment_id and 
                       r['reviewer_id'] == reviewer_id), None)
    
    def calculate_average_rating(self, user_id):
        """Calculate average rating for a user"""
        user_reviews = self.get_reviews_for_user(user_id)
        if not user_reviews:
            return 0.0
        return sum(review['rating'] for review in user_reviews) / len(user_reviews)

# Initialize review manager
review_manager = ReviewManager()


def get_current_user():
    if 'user_id' in session:
        return user_manager.get_user_by_id(session['user_id'])
    return None

def get_providers_by_service(service_key):
    """Get all providers offering a specific service type"""
    providers = []
    for user in user_manager.users:
        if user.get('role') == 'provider' and user.get('service_category') == service_key:
            providers.append({
                'name': user.get('business_name', user.get('name')),
                'username': user.get('username'),
                'description': user.get('business_description', ''),
                'address': user.get('address', ''),
                'rating': 4.5  # Placeholder for future rating system
            })
    return providers

@app.route('/')
def index():
    """Home page - show upcoming appointments"""
    current_user = get_current_user()
    appointments = scheduler.get_appointments()
    # Show only future appointments for logged-in user
    now = datetime.now()
    if current_user:
        upcoming = [apt for apt in appointments if apt['datetime'] >= now and apt.get('user_id') == current_user['id']]
    else:
        upcoming = []
    return render_template('index.html', appointments=upcoming[:5], current_user=current_user)

@app.route('/schedule')
@login_required
def schedule():
    """Schedule appointment page"""
    current_user = get_current_user()
    
    # Get all providers with their availability
    all_providers = [user for user in user_manager.users if user.get('role') == 'provider']
    providers_data = []
    for provider in all_providers:
        providers_data.append({
            'id': provider['id'],
            'name': provider.get('name', ''),
            'business_name': provider.get('business_name', ''),
            'service_category': provider.get('service_category', ''),
            'availability': provider.get('availability', {})
        })
    
    return render_template('schedule.html', 
                         types=scheduler.get_appointment_types(), 
                         current_user=current_user,
                         providers=providers_data)

@app.route('/appointments')
@login_required
def appointments():
    """View all appointments"""
    current_user = get_current_user()
    all_appointments = scheduler.get_appointments()
    # Show only user's appointments
    appointments = [apt for apt in all_appointments if apt.get('user_id') == current_user['id']]
    return render_template('appointments.html', appointments=appointments, current_user=current_user)


@app.route('/history')
@login_required
def history():
    """View appointment history and orders"""
    current_user = get_current_user()
    all_appointments = scheduler.get_appointments()
    # Show only user's appointments
    appointments = [apt for apt in all_appointments if apt.get('user_id') == current_user['id']]
    # Sort by date descending (most recent first)
    appointments.sort(key=lambda x: x['datetime'], reverse=True)
    now = datetime.now()
    return render_template('history.html', appointments=appointments, now=now, current_user=current_user)

@app.route('/profile')
@login_required
def profile():
    """View user profile and information - unified with provider dashboard"""
    current_user = get_current_user()
    all_appointments = scheduler.get_appointments()
    user_appointments = [apt for apt in all_appointments if apt.get('user_id') == current_user['id']]
    
    user_profile = {
        'id': current_user['id'],
        'username': current_user['username'],
        'name': current_user.get('name', current_user['username']),
        'email': current_user.get('email', ''),
        'phone': current_user.get('phone', ''),
        'profile_picture': current_user.get('profile_picture', ''),
        'total_appointments': len(user_appointments),
        'upcoming_appointments': len([apt for apt in user_appointments if apt['datetime'] > datetime.now()]),
        'completed_appointments': len([apt for apt in user_appointments if apt['datetime'] <= datetime.now()])
    }
    
    # Provider-specific data
    provider_data = {}
    if current_user.get('role') == 'provider':
        # Get provider appointments (bookings made by customers for this provider)
        provider_appointments = [apt for apt in all_appointments if apt.get('provider_id') == current_user['id']]
        
        # Calculate provider statistics
        total_bookings = len(provider_appointments)
        completed_count = len([apt for apt in provider_appointments if apt['datetime'] <= datetime.now()])
        pending_count = len([apt for apt in provider_appointments if apt.get('status') == 'pending'])
        
        provider_data = {
            'total_bookings': total_bookings,
            'completed_count': completed_count,
            'pending_count': pending_count
        }
    
    return render_template('profile.html', 
                         user=user_profile, 
                         current_user=current_user,
                         **provider_data)

@app.route('/profile/edit', methods=['POST'])
@login_required
def edit_profile():
    """Update user profile"""
    current_user = get_current_user()
    
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    
    # Handle profile picture upload
    profile_picture = current_user.get('profile_picture', '')
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and file.filename:
            # Read and encode image as base64
            try:
                image_data = file.read()
                if len(image_data) > 0:
                    # Get file extension
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    if ext in ['jpg', 'jpeg', 'png', 'gif']:
                        profile_picture = f"data:image/{ext};base64,{base64.b64encode(image_data).decode()}"
                    else:
                        flash('Invalid image format. Please use JPG, PNG, or GIF.', 'error')
                        return redirect(url_for('profile'))
            except Exception as e:
                flash('Error uploading image. Please try again.', 'error')
                return redirect(url_for('profile'))
    
    # Provider-specific fields
    provider_data = {}
    if current_user.get('role') == 'provider':
        provider_data = {
            'business_name': request.form.get('business_name', '').strip(),
            'business_description': request.form.get('business_description', '').strip(),
            'service_category': request.form.get('service_category', '').strip(),
            'services_offered': request.form.get('services_offered', '').strip(),
            'address': request.form.get('address', '').strip()
        }
    
    # Update user
    if user_manager.update_user(current_user['id'], name=name, email=email, 
                                phone=phone, profile_picture=profile_picture, **provider_data):
        flash('Profile updated successfully!', 'success')
    else:
        flash('Error updating profile.', 'error')
    
    return redirect(url_for('profile'))

@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Delete user account and all associated data"""
    try:
        current_user = get_current_user()
        user_id = current_user['id']
        
        # Delete user from the user manager
        user_manager.users = [user for user in user_manager.users if user['id'] != user_id]
        user_manager.save_users()
        
        # Delete all appointments for this user
        all_appointments = scheduler.get_appointments()
        scheduler.appointments = [apt for apt in all_appointments if apt.get('user_id') != user_id]
        scheduler.save_appointments()
        
        # Clear session
        session.clear()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/help')
def help():
    """View help and support page"""
    current_user = get_current_user()
    # Sample FAQ data
    # All FAQ questions in a single list
    faqs = [
        {
            'question': 'How do I schedule an appointment?',
            'answer': 'Click on "Schedule Appointment" in the navigation menu or on the home page. Fill out the form with your preferred service, date, time, and duration.'
        },
        {
            'question': 'What services do you offer?',
            'answer': 'We offer a wide range of beauty, wellness, and fitness services including hair salon, nail care, massage therapy, personal training, spa treatments, and more. Browse our Services page to see all available options.'
        },
        {
            'question': 'How far in advance can I book?',
            'answer': 'You can book appointments up to 3 months in advance. We recommend booking at least 24 hours ahead for the best availability.'
        },
        {
            'question': 'Do I need to create an account?',
            'answer': 'Yes, creating a free account allows you to manage your appointments, view your history, and receive appointment reminders. Registration takes less than 2 minutes.'
        },
        {
            'question': 'What is your cancellation policy?',
            'answer': 'You can cancel appointments up to 24 hours in advance for a full refund. Cancellations within 24 hours may be subject to a 50% cancellation fee.'
        },
        {
            'question': 'How do I cancel my appointment?',
            'answer': 'Go to your "All Appointments" or "History" page and click the trash icon next to the appointment you want to cancel. You can also contact our support team for assistance.'
        },
        {
            'question': 'What if I need to reschedule?',
            'answer': 'You can reschedule by canceling your current appointment and booking a new one, or contact our support team who can help you find alternative times.'
        },
        {
            'question': 'How long does it take to process refunds?',
            'answer': 'Refunds are typically processed within 3-5 business days and will appear on your original payment method. You\'ll receive an email confirmation once processed.'
        },
        {
            'question': 'I forgot my password. How do I reset it?',
            'answer': 'Click "Forgot Password" on the login page or contact support. We\'ll send you a secure reset link to your registered email address within 5 minutes.'
        },
        {
            'question': 'The website is not loading properly. What should I do?',
            'answer': 'Try refreshing the page, clearing your browser cache, or using a different browser. If the problem persists, contact our technical support team through the chat below.'
        },
        {
            'question': 'Can I use the app on my mobile device?',
            'answer': 'Yes! Our website is fully responsive and works great on mobile phones and tablets. No app download required - just visit our website in your mobile browser.'
        },
        {
            'question': 'I\'m having trouble with the booking form. What should I do?',
            'answer': 'Make sure you have JavaScript enabled and try using a different browser. If the issue continues, contact our technical support team who can help you complete your booking.'
        }
    ]
    
    # Sample support topics
    support_topics = [
        {'id': 'refund', 'title': 'Request Refund', 'icon': 'fas fa-money-bill-wave', 'color': 'danger'},
        {'id': 'reschedule', 'title': 'Reschedule Appointment', 'icon': 'fas fa-calendar-alt', 'color': 'warning'},
        {'id': 'technical', 'title': 'Technical Issue', 'icon': 'fas fa-bug', 'color': 'info'},
        {'id': 'billing', 'title': 'Billing Question', 'icon': 'fas fa-credit-card', 'color': 'primary'},
        {'id': 'general', 'title': 'General Inquiry', 'icon': 'fas fa-question-circle', 'color': 'secondary'}
    ]
    
    return render_template('help.html', faqs=faqs, support_topics=support_topics, current_user=current_user)

def get_services_data():
    """Get all services data - centralized for reuse"""
    # Get real provider counts from database
    return [
        {
            'category': 'Hair & Beauty',
            'icon': 'fas fa-cut',
            'color': 'primary',
            'description': 'Professional hair styling, coloring, and beauty treatments',
            'services': [
                {
                    'name': 'Hair Salon',
                    'description': 'Haircuts, styling, coloring, and treatments',
                    'duration': '60-180 min',
                    'price_range': '$50-$200',
                    'providers': ['Style Studio', 'Hair Masters', 'Beauty Lounge'],
                    'provider_details': get_providers_by_service('hair_salon'),
                    'popular': True
                },
                {
                    'name': 'Nail Salon',
                    'description': 'Manicures, pedicures, nail art, and nail care',
                    'duration': '30-90 min',
                    'price_range': '$25-$80',
                    'providers': ['Nail Art Studio', 'Perfect Nails', 'Luxury Nails'],
                    'provider_details': get_providers_by_service('nail_salon'),
                    'popular': True
                },
                {
                    'name': 'Eyebrow & Eyelash',
                    'description': 'Eyebrow shaping, lash extensions, and tinting',
                    'duration': '45-120 min',
                    'price_range': '$30-$150',
                    'providers': ['Brow Studio', 'Lash Lounge', 'Beauty Bar'],
                    'provider_details': get_providers_by_service('eyebrow_eyelash'),
                    'popular': False
                }
            ]
        },
        {
            'category': 'Wellness & Spa',
            'icon': 'fas fa-spa',
            'color': 'success',
            'description': 'Relaxation, wellness, and therapeutic treatments',
            'services': [
                {
                    'name': 'Massage Therapy',
                    'description': 'Swedish, deep tissue, hot stone, and therapeutic massage',
                    'duration': '60-120 min',
                    'price_range': '$80-$200',
                    'providers': ['Serenity Spa', 'Wellness Center', 'Therapeutic Touch'],
                    'provider_details': get_providers_by_service('massage_therapy'),
                    'popular': True
                },
                {
                    'name': 'Spa Treatment',
                    'description': 'Facials, body wraps, scrubs, and luxury spa services',
                    'duration': '90-240 min',
                    'price_range': '$100-$400',
                    'providers': ['Luxury Spa', 'Zen Wellness', 'Pamper Palace'],
                    'provider_details': get_providers_by_service('spa_treatment'),
                    'popular': True
                },
                {
                    'name': 'Aromatherapy',
                    'description': 'Essential oil treatments and aromatherapy sessions',
                    'duration': '45-90 min',
                    'price_range': '$60-$120',
                    'providers': ['Aroma Wellness', 'Essential Spa', 'Scent Studio'],
                    'provider_details': get_providers_by_service('aromatherapy'),
                    'popular': False
                }
            ]
        },
        {
            'category': 'Fitness & Training',
            'icon': 'fas fa-dumbbell',
            'color': 'warning',
            'description': 'Personal training, fitness classes, and wellness coaching',
            'services': [
                {
                    'name': 'Personal Training',
                    'description': 'One-on-one fitness training and workout sessions',
                    'duration': '60-90 min',
                    'price_range': '$60-$150',
                    'providers': ['FitLife Gym', 'Elite Training', 'Power Fitness'],
                    'provider_details': get_providers_by_service('personal_training'),
                    'popular': True
                },
                {
                    'name': 'Yoga Classes',
                    'description': 'Group and private yoga sessions for all levels',
                    'duration': '60-90 min',
                    'price_range': '$20-$80',
                    'providers': ['Zen Yoga Studio', 'Mindful Movement', 'Peaceful Practice'],
                    'provider_details': get_providers_by_service('yoga_classes'),
                    'popular': True
                },
                {
                    'name': 'Pilates',
                    'description': 'Pilates classes and private sessions',
                    'duration': '45-60 min',
                    'price_range': '$30-$100',
                    'providers': ['Core Pilates', 'Balance Studio', 'Flex Fitness'],
                    'provider_details': get_providers_by_service('pilates'),
                    'popular': False
                }
            ]
        },
        {
            'category': 'Health & Medical',
            'icon': 'fas fa-user-md',
            'color': 'info',
            'description': 'Medical and health-related appointments and treatments',
            'services': [
                {
                    'name': 'Dermatology',
                    'description': 'Skin consultations, treatments, and cosmetic procedures',
                    'duration': '30-90 min',
                    'price_range': '$100-$500',
                    'providers': ['Skin Care Clinic', 'Derma Solutions', 'Beauty Med'],
                    'provider_details': get_providers_by_service('dermatology'),
                    'popular': True
                },
                {
                    'name': 'Physical Therapy',
                    'description': 'Rehabilitation, injury recovery, and mobility improvement',
                    'duration': '45-60 min',
                    'price_range': '$80-$150',
                    'providers': ['Rehab Center', 'Mobility Plus', 'Healing Hands'],
                    'provider_details': get_providers_by_service('physical_therapy'),
                    'popular': True
                },
                {
                    'name': 'Nutrition Counseling',
                    'description': 'Diet planning, nutritional guidance, and wellness coaching',
                    'duration': '60-90 min',
                    'price_range': '$75-$200',
                    'providers': ['Nutrition Plus', 'Healthy Living', 'Wellness Coach'],
                    'provider_details': get_providers_by_service('nutrition_counseling'),
                    'popular': False
                }
            ]
        },
        {
            'category': 'Specialty Services',
            'icon': 'fas fa-star',
            'color': 'secondary',
            'description': 'Unique and specialized personal care services',
            'services': [
                {
                    'name': 'Makeup Artist',
                    'description': 'Professional makeup application for special events',
                    'duration': '60-180 min',
                    'price_range': '$80-$300',
                    'providers': ['Glamour Studio', 'Beauty Artistry', 'Makeup Masters'],
                    'provider_details': get_providers_by_service('makeup_artist'),
                    'popular': True
                },
                {
                    'name': 'Photography',
                    'description': 'Portrait, event, and lifestyle photography sessions',
                    'duration': '60-240 min',
                    'price_range': '$150-$800',
                    'providers': ['Photo Studio Pro', 'Creative Lens', 'Memory Makers'],
                    'provider_details': get_providers_by_service('photography'),
                    'popular': True
                },
                {
                    'name': 'Life Coaching',
                    'description': 'Personal development and life guidance sessions',
                    'duration': '60-90 min',
                    'price_range': '$100-$300',
                    'providers': ['Life Solutions', 'Growth Coaching', 'Success Partners'],
                    'provider_details': get_providers_by_service('life_coaching'),
                    'popular': False
                }
            ]
        }
    ]

@app.route('/services')
def services():
    """View available services and providers"""
    current_user = get_current_user()
    services_data = get_services_data()
    return render_template('services.html', services=services_data, current_user=current_user)

@app.route('/add_appointment', methods=['POST'])
@login_required
def add_appointment():
    """Add new appointment"""
    current_user = get_current_user()
    appointment_type_key = request.form.get('type')
    date = request.form.get('date')
    time = request.form.get('time')
    duration = int(request.form.get('duration'))
    notes = request.form.get('notes', '')
    provider_id = request.form.get('provider_id')
    
    # Convert to integer if provided
    provider_id = int(provider_id) if provider_id else None
    
    # Convert key to display name (e.g., "hair" -> "Hair Salon")
    appointment_type = scheduler.appointment_types.get(appointment_type_key, appointment_type_key)
    
    if scheduler.add_appointment(appointment_type, date, time, duration, notes, 
                                 user_id=current_user['id'], provider_id=provider_id):
        flash('Appointment request submitted! Waiting for provider confirmation.', 'success')
    else:
        flash('Failed to schedule appointment. Time slot may be unavailable.', 'error')
    
    return redirect(url_for('appointments'))

@app.route('/cancel_appointment/<int:appointment_id>', methods=['POST'])
def cancel_appointment(appointment_id):
    """Cancel an appointment"""
    if scheduler.cancel_appointment(appointment_id):
        flash('Appointment cancelled successfully!', 'success')
    else:
        flash('Appointment not found.', 'error')
    
    return redirect(url_for('appointments'))


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for customers and providers"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')
        
        user = user_manager.authenticate(username, password)
        if user:
            session.permanent = True  # Make session persistent
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user.get('role', 'consumer')
            
            name = user.get('name', user['username'])
            flash(f'Welcome back, {name}!', 'success')
            
            # Redirect to profile page for all users (unified)
            return redirect(url_for('profile'))
        else:
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page for customers and providers"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        # If no name provided, use username as default
        if not name:
            name = username
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'consumer')
        
        # Basic validation
        if not username or not password or not email:
            flash('Username, email, and password are required.', 'error')
            return render_template('register.html')
        
        # Role-specific validation
        if role == 'consumer' and not name:
            flash('Full name is required for customer accounts.', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        if len(password) < 4:
            flash('Password must be at least 4 characters long.', 'error')
            return render_template('register.html')
        
        # Provider-specific validation and fields
        provider_data = {}
        if role == 'provider':
            business_name = request.form.get('business_name', '').strip()
            service_category = request.form.get('service_category', '').strip()
            business_description = request.form.get('business_description', '').strip()
            services_offered = request.form.get('services_offered', '').strip()
            address = request.form.get('address', '').strip()
            
            if not business_name:
                flash('Business name is required for service providers.', 'error')
                return render_template('register.html')
            
            if not service_category:
                flash('Service category is required for service providers.', 'error')
                return render_template('register.html')
            
            provider_data = {
                'business_name': business_name,
                'service_category': service_category,
                'business_description': business_description,
                'services_offered': services_offered,
                'address': address
            }
        
        # Create user
        if user_manager.create_user(username, password, email, role, name=name, phone=phone, **provider_data):
            if role == 'provider':
                flash('Provider account created successfully! Please log in to access your profile.', 'success')
            else:
                flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Username already exists.', 'error')
    
    return render_template('register.html')

def get_providers_with_ratings(service_category):
    """Helper function to get providers with rating information"""
    all_providers = [user for user in user_manager.users if user.get('role') == 'provider']
    providers = []
    for provider in all_providers:
        if provider.get('service_category') == service_category:
            provider_data = {k: v for k, v in provider.items() if k != 'password'}
            # Add rating information
            provider_data['average_rating'] = review_manager.calculate_average_rating(provider['id'])
            provider_data['total_reviews'] = len(review_manager.get_reviews_for_user(provider['id']))
            providers.append(provider_data)
    return providers

@app.route('/providers/hair-salon')
def hair_providers():
    """View hair salon providers"""
    current_user = get_current_user()
    hair_providers = get_providers_with_ratings('hair_salon')
    return render_template('hair_providers.html', providers=hair_providers, current_user=current_user)

@app.route('/providers/nail-salon')
def nail_providers():
    """View nail salon providers"""
    current_user = get_current_user()
    nail_providers = get_providers_with_ratings('nail_salon')
    return render_template('nail_providers.html', providers=nail_providers, current_user=current_user)

@app.route('/providers/massage-therapy')
def massage_providers():
    """View massage therapy providers"""
    current_user = get_current_user()
    massage_providers = get_providers_with_ratings('massage_therapy')
    return render_template('massage_providers.html', providers=massage_providers, current_user=current_user)

@app.route('/providers/spa-treatment')
def spa_providers():
    """View spa treatment providers"""
    current_user = get_current_user()
    spa_providers = get_providers_with_ratings('spa_treatment')
    return render_template('spa_providers.html', providers=spa_providers, current_user=current_user)

@app.route('/providers/personal-training')
def training_providers():
    """View personal training providers"""
    current_user = get_current_user()
    training_providers = get_providers_with_ratings('personal_training')
    return render_template('training_providers.html', providers=training_providers, current_user=current_user)

@app.route('/providers/yoga-classes')
def yoga_providers():
    """View yoga classes providers"""
    current_user = get_current_user()
    yoga_providers = get_providers_with_ratings('yoga_classes')
    return render_template('yoga_providers.html', providers=yoga_providers, current_user=current_user)

@app.route('/providers/eyebrow-eyelash')
def eyebrow_providers():
    """View eyebrow & eyelash providers"""
    current_user = get_current_user()
    eyebrow_providers = get_providers_with_ratings('eyebrow_eyelash')
    return render_template('eyebrow_providers.html', providers=eyebrow_providers, current_user=current_user)

@app.route('/providers/aromatherapy')
def aromatherapy_providers():
    """View aromatherapy providers"""
    current_user = get_current_user()
    aromatherapy_providers = get_providers_with_ratings('aromatherapy')
    return render_template('aromatherapy_providers.html', providers=aromatherapy_providers, current_user=current_user)

@app.route('/providers/pilates')
def pilates_providers():
    """View pilates providers"""
    current_user = get_current_user()
    pilates_providers = get_providers_with_ratings('pilates')
    return render_template('pilates_providers.html', providers=pilates_providers, current_user=current_user)

@app.route('/providers/dermatology')
def dermatology_providers():
    """View dermatology providers"""
    current_user = get_current_user()
    dermatology_providers = get_providers_with_ratings('dermatology')
    return render_template('dermatology_providers.html', providers=dermatology_providers, current_user=current_user)

@app.route('/providers/physical-therapy')
def physical_therapy_providers():
    """View physical therapy providers"""
    current_user = get_current_user()
    physical_therapy_providers = get_providers_with_ratings('physical_therapy')
    return render_template('physical_therapy_providers.html', providers=physical_therapy_providers, current_user=current_user)

@app.route('/providers/nutrition-consulting')
def nutrition_providers():
    """View nutrition consulting providers"""
    current_user = get_current_user()
    nutrition_providers = get_providers_with_ratings('nutrition_counseling')
    return render_template('nutrition_providers.html', providers=nutrition_providers, current_user=current_user)

@app.route('/providers/makeup-artist')
def makeup_providers():
    """View makeup artist providers"""
    current_user = get_current_user()
    makeup_providers = get_providers_with_ratings('makeup_artist')
    return render_template('makeup_providers.html', providers=makeup_providers, current_user=current_user)

@app.route('/providers/photography')
def photography_providers():
    """View photography providers"""
    current_user = get_current_user()
    photography_providers = get_providers_with_ratings('photography')
    return render_template('photography_providers.html', providers=photography_providers, current_user=current_user)

@app.route('/find-near-you')
def find_near_you():
    """Find providers near user location"""
    current_user = get_current_user()
    return render_template('find_near_you.html', current_user=current_user)

@app.route('/api/providers')
def api_providers():
    """API endpoint to get all providers with their location data"""
    providers = []
    for user in user_manager.users:
        if user.get('role') == 'provider' and user.get('address'):
            provider_data = {
                'id': user['id'],
                'business_name': user.get('business_name', ''),
                'service_category': user.get('service_category', ''),
                'address': user.get('address', ''),
                'business_description': user.get('business_description', ''),
                'services_offered': user.get('services_offered', ''),
                'phone': user.get('phone', ''),
                'email': user.get('email', '')
            }
            providers.append(provider_data)
    return jsonify(providers)

@app.route('/providers/life-coaching')
def lifecoaching_providers():
    """View life coaching providers"""
    current_user = get_current_user()
    lifecoaching_providers = get_providers_with_ratings('life_coaching')
    return render_template('lifecoaching_providers.html', providers=lifecoaching_providers, current_user=current_user)



@app.route('/appointment/<int:appointment_id>/complete', methods=['POST'])
@login_required
def complete_appointment(appointment_id):
    """Mark an appointment as completed"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can complete appointments'}), 403
    
    try:
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == appointment_id), None)
        
        if not appointment:
            return jsonify({'success': False, 'error': 'Appointment not found'}), 404
        
        if appointment.get('provider_id') != current_user['id']:
            return jsonify({'success': False, 'error': 'Not your appointment'}), 403
        
        if appointment.get('status') != 'confirmed':
            return jsonify({'success': False, 'error': 'Only confirmed appointments can be completed'}), 400
        
        # Check if appointment time has been reached
        appointment_datetime = appointment.get('datetime')
        if appointment_datetime:
            if isinstance(appointment_datetime, str):
                appointment_datetime = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00'))
            
            current_time = datetime.now()
            if current_time < appointment_datetime:
                return jsonify({'success': False, 'error': 'Cannot complete appointment before its scheduled time'}), 400
        
        appointment['status'] = 'completed'
        appointment['completed_at'] = datetime.now().isoformat()
        scheduler.save_appointments()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/profile/availability/update', methods=['POST'])
@login_required
def update_availability():
    """Update provider availability"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can set availability'}), 403
    
    try:
        availability_data = request.get_json()
        
        # Get user from database
        user = next((u for u in user_manager.users if u['id'] == current_user['id']), None)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Update availability
        user['availability'] = availability_data
        user_manager.save_users()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/appointment/<int:appointment_id>/review', methods=['GET', 'POST'])
@login_required
def review_appointment(appointment_id):
    """Review an appointment - both customer and provider can review"""
    current_user = get_current_user()
    
    # Find the appointment
    appointment = next((apt for apt in scheduler.appointments if apt['id'] == appointment_id), None)
    
    # Determine redirect page based on user role
    if current_user.get('role') == 'provider':
        redirect_page = url_for('provider_appointments')
    else:
        redirect_page = url_for('history')
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(redirect_page)
    
    # Check if user is involved in this appointment
    if (appointment.get('user_id') != current_user['id'] and 
        appointment.get('provider_id') != current_user['id']):
        flash('You can only review appointments you are involved in.', 'error')
        return redirect(redirect_page)
    
    # Check if appointment is completed
    if appointment.get('status') != 'completed':
        flash('You can only review completed appointments.', 'error')
        return redirect(redirect_page)
    
    # Check if user already reviewed this appointment
    existing_review = review_manager.get_review_for_appointment(appointment_id, current_user['id'])
    if existing_review:
        flash('You have already reviewed this appointment.', 'error')
        return redirect(redirect_page)
    
    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()
        
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                flash('Rating must be between 1 and 5 stars.', 'error')
                return render_template('review_form.html', appointment=appointment, current_user=current_user)
        except (ValueError, TypeError):
            flash('Please select a valid rating.', 'error')
            return render_template('review_form.html', appointment=appointment, current_user=current_user)
        
        # Determine who is being reviewed
        if appointment.get('user_id') == current_user['id']:
            # Customer is reviewing the provider
            reviewed_id = appointment.get('provider_id')
        else:
            # Provider is reviewing the customer
            reviewed_id = appointment.get('user_id')
        
        if review_manager.add_review(appointment_id, current_user['id'], reviewed_id, rating, comment):
            flash('Review submitted successfully!', 'success')
            # Redirect based on user role
            if current_user.get('role') == 'provider':
                return redirect(url_for('provider_appointments'))
            else:
                return redirect(url_for('history'))
        else:
            flash('Failed to submit review. Please try again.', 'error')
    
    return render_template('review_form.html', appointment=appointment, current_user=current_user)

@app.route('/reviews')
@login_required
def reviews():
    """View all reviews for the current user"""
    current_user = get_current_user()
    
    # Get reviews received by this user
    received_reviews = review_manager.get_reviews_for_user(current_user['id'])
    
    # Get reviews written by this user
    written_reviews = review_manager.get_reviews_by_user(current_user['id'])
    
    # Calculate average rating
    average_rating = review_manager.calculate_average_rating(current_user['id'])
    
    # Add reviewer/reviewed user names to reviews
    for review in received_reviews + written_reviews:
        reviewer = user_manager.get_user_by_id(review['reviewer_id'])
        reviewed = user_manager.get_user_by_id(review['reviewed_id'])
        review['reviewer_name'] = reviewer.get('name', reviewer.get('username', 'Unknown')) if reviewer else 'Unknown'
        review['reviewed_name'] = reviewed.get('name', reviewed.get('username', 'Unknown')) if reviewed else 'Unknown'
        
        # Get appointment details
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == review['appointment_id']), None)
        review['appointment_type'] = appointment.get('type', 'Unknown') if appointment else 'Unknown'
    
    return render_template('reviews.html', 
                         received_reviews=received_reviews,
                         written_reviews=written_reviews,
                         average_rating=average_rating,
                         current_user=current_user)

@app.route('/api/reviews/<int:user_id>')
def api_user_reviews(user_id):
    """API endpoint to get reviews for a specific user"""
    reviews = review_manager.get_reviews_for_user(user_id)
    average_rating = review_manager.calculate_average_rating(user_id)
    
    # Add reviewer names
    for review in reviews:
        reviewer = user_manager.get_user_by_id(review['reviewer_id'])
        review['reviewer_name'] = reviewer.get('name', reviewer.get('username', 'Anonymous')) if reviewer else 'Anonymous'
    
    return jsonify({
        'reviews': reviews,
        'average_rating': round(average_rating, 1),
        'total_reviews': len(reviews)
    })



@app.route('/provider/<int:provider_id>')
def provider_profile(provider_id):
    """Individual provider profile page"""
    current_user = get_current_user()
    
    # Get provider information
    provider = user_manager.get_user_by_id(provider_id)
    if not provider or provider.get('role') != 'provider':
        flash('Provider not found.', 'error')
        return redirect(url_for('index'))
    
    # Get reviews for this provider
    provider_reviews = review_manager.get_reviews_for_user(provider_id)
    average_rating = review_manager.calculate_average_rating(provider_id)
    
    # Add reviewer names and appointment details
    for review in provider_reviews:
        reviewer = user_manager.get_user_by_id(review['reviewer_id'])
        review['reviewer_name'] = reviewer.get('name', reviewer.get('username', 'Anonymous')) if reviewer else 'Anonymous'
        
        # Get appointment details
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == review['appointment_id']), None)
        review['appointment_type'] = appointment.get('type', 'Unknown') if appointment else 'Unknown'
    
    # Sort reviews by most recent first
    provider_reviews.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Get provider's upcoming appointments (for availability indication)
    all_appointments = scheduler.get_appointments()
    provider_appointments = [apt for apt in all_appointments 
                           if apt.get('provider_id') == provider_id and 
                              apt.get('status') in ['confirmed', 'pending'] and
                              apt['datetime'] >= datetime.now()]
    
    return render_template('provider_profile.html', 
                         provider=provider,
                         reviews=provider_reviews,
                         average_rating=average_rating,
                         total_reviews=len(provider_reviews),
                         upcoming_appointments=len(provider_appointments),
                         current_user=current_user)

@app.route('/provider/<int:provider_id>/reviews')
def provider_reviews(provider_id):
    """View all reviews for a specific provider - public access for customers"""
    current_user = get_current_user()
    
    # Get provider information
    provider = user_manager.get_user_by_id(provider_id)
    if not provider or provider.get('role') != 'provider':
        flash('Provider not found.', 'error')
        return redirect(url_for('index'))
    
    # Get reviews for this provider
    provider_reviews = review_manager.get_reviews_for_user(provider_id)
    average_rating = review_manager.calculate_average_rating(provider_id)
    
    # Add reviewer names and appointment details
    for review in provider_reviews:
        reviewer = user_manager.get_user_by_id(review['reviewer_id'])
        review['reviewer_name'] = reviewer.get('name', reviewer.get('username', 'Anonymous')) if reviewer else 'Anonymous'
        
        # Get appointment details
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == review['appointment_id']), None)
        review['appointment_type'] = appointment.get('type', 'Unknown') if appointment else 'Unknown'
    
    # Sort by most recent first
    provider_reviews.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template('provider_reviews.html', 
                         provider=provider,
                         reviews=provider_reviews,
                         average_rating=average_rating,
                         total_reviews=len(provider_reviews),
                         current_user=current_user)

@app.route('/provider/appointments')
@login_required
def provider_appointments():
    """Provider appointment management page"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        flash('Only providers can access this page.', 'error')
        return redirect(url_for('profile'))
    
    # Get all appointments for this provider
    all_appointments = scheduler.get_appointments()
    provider_appointments = [apt for apt in all_appointments if apt.get('provider_id') == current_user['id']]
    
    # Separate by status
    pending_appointments = [apt for apt in provider_appointments if apt.get('status') == 'pending']
    confirmed_appointments = [apt for apt in provider_appointments if apt.get('status') == 'confirmed']
    completed_appointments = [apt for apt in provider_appointments if apt.get('status') == 'completed']
    
    # Add customer names to appointments
    for apt in provider_appointments:
        customer = user_manager.get_user_by_id(apt.get('user_id'))
        apt['customer_name'] = customer.get('name', customer.get('username', 'Unknown')) if customer else 'Unknown'
        apt['customer_phone'] = customer.get('phone', '') if customer else ''
        apt['customer_email'] = customer.get('email', '') if customer else ''
    
    return render_template('provider_appointments.html', 
                         pending_appointments=pending_appointments,
                         confirmed_appointments=confirmed_appointments,
                         completed_appointments=completed_appointments,
                         current_user=current_user,
                         now=datetime.now())

@app.route('/appointment/<int:appointment_id>/confirm', methods=['POST'])
@login_required
def confirm_appointment(appointment_id):
    """Confirm a pending appointment"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can confirm appointments'}), 403
    
    try:
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == appointment_id), None)
        
        if not appointment:
            return jsonify({'success': False, 'error': 'Appointment not found'}), 404
        
        if appointment.get('provider_id') != current_user['id']:
            return jsonify({'success': False, 'error': 'Not your appointment'}), 403
        
        if appointment.get('status') != 'pending':
            return jsonify({'success': False, 'error': 'Only pending appointments can be confirmed'}), 400
        
        appointment['status'] = 'confirmed'
        scheduler.save_appointments()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/appointment/<int:appointment_id>/decline', methods=['POST'])
@login_required
def decline_appointment(appointment_id):
    """Decline a pending appointment"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can decline appointments'}), 403
    
    try:
        appointment = next((apt for apt in scheduler.appointments if apt['id'] == appointment_id), None)
        
        if not appointment:
            return jsonify({'success': False, 'error': 'Appointment not found'}), 404
        
        if appointment.get('provider_id') != current_user['id']:
            return jsonify({'success': False, 'error': 'Not your appointment'}), 403
        
        if appointment.get('status') != 'pending':
            return jsonify({'success': False, 'error': 'Only pending appointments can be declined'}), 400
        
        appointment['status'] = 'declined'
        scheduler.save_appointments()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/provider/gallery/upload', methods=['POST'])
@login_required
def upload_gallery_image():
    """Upload image to provider gallery"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can upload gallery images'}), 403
    
    try:
        if 'gallery_image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['gallery_image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No image selected'}), 400
        
        # Validate file type
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                return jsonify({'success': False, 'error': 'Invalid image format. Please use JPG, PNG, GIF, or WebP.'}), 400
            
            # Read and encode image as base64
            image_data = file.read()
            if len(image_data) > 5 * 1024 * 1024:  # 5MB limit
                return jsonify({'success': False, 'error': 'Image too large. Maximum size is 5MB.'}), 400
            
            # Get user from database
            user = next((u for u in user_manager.users if u['id'] == current_user['id']), None)
            if not user:
                return jsonify({'success': False, 'error': 'User not found'}), 404
            
            # Initialize gallery if it doesn't exist
            if 'gallery' not in user:
                user['gallery'] = []
            
            # Create gallery image entry
            gallery_image = {
                'id': len(user['gallery']) + 1,
                'filename': file.filename,
                'data': f"data:image/{ext};base64,{base64.b64encode(image_data).decode()}",
                'uploaded_at': datetime.now().isoformat(),
                'description': request.form.get('description', '').strip()
            }
            
            user['gallery'].append(gallery_image)
            user_manager.save_users()
            
            return jsonify({'success': True, 'image_id': gallery_image['id']})
        
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/provider/gallery/delete/<int:image_id>', methods=['POST'])
@login_required
def delete_gallery_image(image_id):
    """Delete image from provider gallery"""
    current_user = get_current_user()
    
    if current_user.get('role') != 'provider':
        return jsonify({'success': False, 'error': 'Only providers can delete gallery images'}), 403
    
    try:
        # Get user from database
        user = next((u for u in user_manager.users if u['id'] == current_user['id']), None)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        if 'gallery' not in user:
            return jsonify({'success': False, 'error': 'No gallery found'}), 404
        
        # Find and remove the image
        original_length = len(user['gallery'])
        user['gallery'] = [img for img in user['gallery'] if img['id'] != image_id]
        
        if len(user['gallery']) == original_length:
            return jsonify({'success': False, 'error': 'Image not found'}), 404
        
        user_manager.save_users()
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

