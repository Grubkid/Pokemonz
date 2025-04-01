import os, csv
import datetime
from flask import Flask, request, redirect, render_template, url_for, flash
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
    current_user
)
from .models import db, User, UserPokemon, Pokemon

# Configure Flask App
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'MySecretKey'
app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token'
app.config['JWT_REFRESH_COOKIE_NAME'] = 'refresh_token'
app.config["JWT_TOKEN_LOCATION"] = ["cookies", "headers"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = datetime.timedelta(hours=15)
app.config["JWT_COOKIE_SECURE"] = False
app.config["JWT_SECRET_KEY"] = "super-secret"
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
app.config['JWT_HEADER_NAME'] = "Cookie"


# Initialize App 
db.init_app(app)
app.app_context().push()
CORS(app)
jwt = JWTManager(app)
# JWT Config to enable current_user
@jwt.user_identity_loader
def user_identity_lookup(user):
  return user.id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
  identity = jwt_data["sub"]
  return User.query.get(identity)

# *************************************

# Initializer Function to be used in both init command and /init route
# Parse pokemon.csv and populate database and creates user "bob" with password "bobpass"
def initialize_db():
  db.drop_all()
  db.create_all()
  with open('pokemon.csv', newline='', encoding='utf8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
      if row['height_m'] == '':
        row['height_m'] = None
      if row['weight_kg'] == '':
        row['weight_kg'] = None
      if row['type2'] == '':
        row['type2'] = None

      pokemon = Pokemon(name=row['name'], attack=row['attack'], defense=row['defense'], sp_attack=row['sp_attack'], sp_defense=row['sp_defense'], weight=row['weight_kg'], height=row['height_m'], hp=row['hp'], speed=row['speed'], type1=row['type1'], type2=row['type2'])
      db.session.add(pokemon)
    bob = User(username='bob', email="bob@mail.com", password="bobpass")
    db.session.add(bob)
    db.session.commit()
    bob.catch_pokemon(1, "Benny")
    bob.catch_pokemon(25, "Saul")

# ********** Routes **************

# Template implementation (don't change)

@app.route('/init')
def init_route():
  initialize_db()
  return redirect(url_for('login_page'))

@app.route("/", methods=['GET'])
def login_page():
  return render_template("login.html")

@app.route("/signup", methods=['GET'])
def signup_page():
    return render_template("signup.html")

@app.route("/signup", methods=['POST'])
def signup_action():
  response = None
  try:
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    user = User(username=username, email=email, password=password)
    db.session.add(user)
    db.session.commit()
    response = redirect(url_for('home_page'))
    token = create_access_token(identity=user)
    set_access_cookies(response, token)
  except IntegrityError:
    flash('Username already exists')
    response = redirect(url_for('signup_page'))
  flash('Account created')
  return response

@app.route("/logout", methods=['GET'])
@jwt_required()
def logout_action():
  response = redirect(url_for('login_page'))
  unset_jwt_cookies(response)
  flash('Logged out')
  return response

# *************************************

# Page Routes (To Update)

@app.route("/app", methods=['GET'])
@app.route("/app/<int:pokemon_id>", methods=['GET'])
@jwt_required()
def home_page(pokemon_id=1):
    # update pass relevant data to template
    all_pokemon = Pokemon.query.order_by(Pokemon.id).all()
    selected_pokemon = Pokemon.query.get(pokemon_id) or Pokemon.query.get(1)
    captured_pokemon = current_user.pokemon
    return render_template(
        "home.html",
        pokemon_list=all_pokemon,
        selected_pokemon=selected_pokemon,
        captured_pokemon=captured_pokemon
    )

# Action Routes (To Update)

@app.route("/login", methods=['POST'])
def login_action():
    username = request.form.get('username')
    password = request.form.get('password')
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        response = redirect(url_for('home_page'))
        token = create_access_token(identity=user)
        set_access_cookies(response, token)
        flash('Logged in successfully')
        return response
    else:
        flash('Invalid credentials')
        return redirect(url_for('login_page'))

@app.route("/pokemon/<int:pokemon_id>", methods=['POST'])
@jwt_required()
def capture_action(pokemon_id):
    pokemon_name = request.form.get('pokemon_name', '').strip()
    
    if not pokemon_name:
        flash('Please provide a name for your Pokemon')
        return redirect(url_for('home_page'))
    
    pokemon = Pokemon.query.get(pokemon_id)
    if not pokemon:
        flash('Invalid Pokemon')
        return redirect(url_for('home_page'))
    
    new_capture = current_user.catch_pokemon(pokemon_id, pokemon_name)
    if new_capture:
        flash(f'Successfully captured {pokemon_name}!')
        db.session.commit()  
    else:
        flash('Capture failed - you may already have this Pokemon')
    
    return redirect(url_for('home_page'))

@app.route("/rename-pokemon/<int:user_pokemon_id>", methods=['POST'])
@jwt_required()
def rename_action(user_pokemon_id):
    new_name = request.form.get('pokemon_name', '').strip()

    if not new_name:
        flash('Please provide a new name for your Pokemon', 'error')
        return redirect(request.referrer)
    
    user_pokemon = UserPokemon.query.filter_by(id=user_pokemon_id, user_id=current_user.id).first()
    
    if not user_pokemon:
        flash('Pokemon not found in your collection', 'error')
        return redirect(request.referrer)

    try:
        user_pokemon.name = new_name
        db.session.add(user_pokemon) 
        db.session.commit()
        flash(f'Pokemon renamed to {new_name}!', 'success')
    except Exception as e:
        print(f"Error renaming Pokemon: {e}")
        db.session.rollback()
        flash('An error occurred while renaming the Pokemon', 'error')
    
    return redirect(request.referrer)


@app.route("/release-pokemon/<int:user_pokemon_id>", methods=['POST'])
@jwt_required()
def release_action(user_pokemon_id):

    user_pokemon = UserPokemon.query.filter_by(id=user_pokemon_id, user_id=current_user.id).first()
    
    if not user_pokemon:
        flash('Pokemon not found in your collection', 'error')
        return redirect(request.referrer)

    try:
        db.session.delete(user_pokemon)
        db.session.commit()
        flash('Pokemon released!', 'success')
    except Exception as e:
        print(f"Error releasing Pokemon: {e}")
        db.session.rollback()
        flash('An error occurred while releasing the Pokemon', 'error')
  
    return redirect(request.referrer)


if __name__ == "__main__":
  app.run(host='0.0.0.0', port=8080)