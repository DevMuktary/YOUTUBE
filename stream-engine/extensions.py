from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager

# Initialize these here so other files can use them
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()
