from flask import Blueprint, request, jsonify
from extensions import db, bcrypt, jwt
from models import User
from flask_jwt_extended import create_access_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    # 1. Validation
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Missing email or password"}), 400

    # 2. Check Exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"error": "Email already exists"}), 409

    # 3. Hash & Save
    hashed = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(
        full_name=data.get('full_name', 'User'),
        email=data['email'],
        password_hash=hashed
    )
    
    try:
        db.session.add(new_user)
        db.session.commit()
        
        # 4. Generate Token
        token = create_access_token(identity=str(new_user.id))
        return jsonify({
            "message": "User created",
            "access_token": token,
            "user": new_user.to_dict()
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()

    if user and bcrypt.check_password_hash(user.password_hash, data.get('password')):
        token = create_access_token(identity=str(user.id))
        return jsonify({
            "access_token": token,
            "user": user.to_dict()
        }), 200
        
    return jsonify({"error": "Invalid credentials"}), 401
