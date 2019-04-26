#Importing required libreries:
import pandas as pd
from flask import Flask,jsonify, json, request, g, url_for, abort
import requests
import itertools
from flask_httpauth import HTTPBasicAuth
from flask_sqlalchemy import SQLAlchemy
import plotly.graph_objs as go
import plotly.plotly as py
import os
import requests_cache
from passlib.apps import custom_app_context as pwd_context
from itsdangerous import (TimedJSONWebSignatureSerializer as Serializer, BadSignature, SignatureExpired)

#Calling "install_cache" to avoid running the same request twice:
requests_cache.install_cache('crime_api_cache', backend='sqlite', expire_after=36000)


#Calling "Flask" to create an app:
app = Flask(__name__, instance_relative_config=True)


#Setting up configurations of the app:
app.config.from_object('config') 
app.config.from_pyfile('config.py')
app.config.from_object('users') 
app.config.from_pyfile('users.py')
SECRET_KEY = app.config['SECRET_KEY']
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

#Creating Extensions:
db = SQLAlchemy(app)
auth = HTTPBasicAuth()


#Creating a Class object "User": 
class User(db.Model):
    
    #Defining the tablename in the User Object:
    __tablename__ = 'users'
    
    #Defining the different columns for the table:
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(64))

    #Method takes a plain password as argument:
    def hash_password(self, password):
        #It stores a hash of it with the user:
        self.password_hash = pwd_context.encrypt(password)

    #Method takes a plain password as argument:
    def verify_password(self, password):
        #It returns "True" if the password is correct or "False" if not:
        return pwd_context.verify(password, self.password_hash)

    #Method generates an encrypted version of a dictionary with an expiration time of 600seconds:
    def generate_auth_token(self, expiration=600):
        s = Serializer(app.config['SECRET_KEY'], expires_in=expiration)
        #The dictionary that is return has the id of the user:
        return s.dumps({'id': self.id})

    #Method generates a verification for the token:
    @staticmethod # A static method is used because the user will only be known once the token is decoded
    def verify_auth_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None    # Return if Valid token, but expired
        except BadSignature:
            return None    # Return if Invalid token
        user = User.query.get(data['id'])
        return user

#Defining a new "verify_password" function which supports both authentication methods (Username/Password; Token):
@auth.verify_password
def verify_password(username_or_token, password):
    #First try to authenticate by token:
    user = User.verify_auth_token(username_or_token)
    if not user:
        #If not try to authenticate with username/password
        user = User.query.filter_by(username=username_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True


@app.route('/api/users', methods=['POST']) #The "/api/users" Path calls the function
def new_user():
    username = request.json.get('username') #Extracting the username from the Json request
    password = request.json.get('password') #Extracting the password from the Json request
    if username is None or password is None:
        abort(400)    # Abort request if any missing arguments
    if User.query.filter_by(username=username).first() is not None:
        abort(400)    # Abort request if it is an extisting user
        
    #If the arguments are valid then a new User instance is created:
    user = User(username=username) #Assign username
    user.hash_password(password) #Hash the password using the hash_password()
    
    #The user is finally written to the database:
    db.session.add(user) 
    db.session.commit()
    
    #Return the succesful request:
    return (jsonify({'username': user.username}), 201)


@app.route('/api/users/<int:id>/<secret_key>', methods=['GET'])
def get_user(id, secret_key): #get_user" has one paramter
    
    #Secret key is a paramter just known to the admin:
    if secret_key == SECRET_KEY:
        #Querying the user for the given id:
        user = User.query.get(id)

       #If the id is not in the user table abort the request:
        if not user:
            abort(400)

        #If the id is in user table then return the username for the given userid
        return jsonify({'username': user.username})
    
    #Else return a suggestion:
    else:
        return "Your secret_key parameter is wrong"


@app.route('/api/all_users_names/<secret_key>', methods=['GET'])
def get_all_usernames(secret_key): #"get_all_usernamers" has one paramter "secret_key"
    
    #Secret key is a paramter just known to the admin:
    if secret_key == SECRET_KEY:
        #If the admin is authenticated then query all parameters:
        users = User.query.all()

        #Open an empty list:
        names = []
        
        #Iterate through all records:
        for user in users:
            
            #Append records to names:
            names.append(user.username)
        
        #Return the records in a json format
        return jsonify(names)
    
    #Else return a suggestion:
    else:
        return "Your secret_key parameter is wrong"

@app.route('/api/all_users_ids/<secret_key>', methods=['GET'])
def get_all_userids(secret_key): #"get_all_userids" has one paramter "secret_key"
    
    #Secret key is a paramter just known to the admin:
    if secret_key == SECRET_KEY:
        #If the admin is authenticated then query all parameters:
        users = User.query.all()

        #Open an empty list:
        ids = []
        
        #Iterate through all records:
        for user in users:
            
            #Append records to names:
            ids.append(user.id)
        
        #Return the records in a json format
        return jsonify(ids)
    
    #Else return a suggestion:
    else:
        return "Your secret_key parameter is wrong"


@app.route('/api/token')
@auth.login_required #To generate the token a the user needs to authenticate himself:
def get_auth_token():
    token = g.user.generate_auth_token(600) #Generate the token
    return jsonify({'token': token.decode('ascii'), 'duration': 600}) #Return the token with a duration of 600 seconds

#Defining support Function "clean_col":
def clean_col(inputlst):
    col_list = []
    for col in inputlst:
        col = col.strip()
        col = col.lower()
        col = col.replace(" ", "_")
        col = col.replace("(", "")
        col = col.replace(")", "")
        col = col.replace("-", "_")
        col = col.strip()
        col_list.append(col)
    return col_list

#Calling "errorhandler" to receive an error message if the request returns 404:
@app.errorhandler(404)
def page_not_found(e):
    return  "There has been an error", 404


@app.route('/api/all_crime_data/<date>/<n_records>/<csv>', methods = ['GET'])#The "/all_crime_data/<date>/<n_records>" Path calls the function
@auth.login_required
def get_records(date, n_records, csv): #"get_records" has 3 parameters:
                                      #1. "date" parameter
                                      #2. "n_records" paramter, which can be either All or an interger
                                      #3. "csv" is given to allow the user to extract a csv
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        all_crime_data = resp.json()

    #Else return the "status_code" of the respons:
    else:
        print(resp.status_code)
    
    #Creating a set of list to assign each value for each entry in the dictionary (see Mini_Project.ipynb)
    codes = []
    procedures = []
    dates = []
    person_ids = []
    crime_categories = []
    location_types = []
    latitudes = []
    longitudes = []
    street_ids = []
    street_names = []
    contexts = []
    persistent_ids = []
    crime_ids = []
    location_subtypes = []
    months = []

    #Calling a loop for every entry in the dictionary that has been returned from the response:
    for i in range(len(all_crime_data)):

    #Assigning each "i" value for each iteration to a variable:
        code = all_crime_data[i]["category"]["code"]
        procedure = all_crime_data[i]["category"]["name"]
        date =  all_crime_data[i]["date"]
        person_id = all_crime_data[i]["person_id"]
        crime_category = all_crime_data[i]["crime"]["category"]
        location_type = all_crime_data[i]["crime"]["location_type"]
        latitude = all_crime_data[i]["crime"]["location"]["latitude"]
        longitude = all_crime_data[i]["crime"]["location"]["longitude"]
        street_id = all_crime_data[i]["crime"]["location"]["street"]["id"]
        street_name = all_crime_data[i]["crime"]["location"]["street"]["name"]
        context = all_crime_data[i]["crime"]["context"]
        persistent_id = all_crime_data[i]["crime"]["persistent_id"]
        crime_id = all_crime_data[i]["crime"]["id"]
        location_subtype = all_crime_data[i]["crime"]["location_subtype"]
        month = all_crime_data[i]["crime"]["month"]
        
    #Appending each variable to the respective list:
        codes.append(code)
        procedures.append(procedure)
        dates.append(date)
        person_ids.append(person_id)
        crime_categories.append(crime_category)
        location_types.append(location_type)
        latitudes.append(latitude)
        longitudes.append(longitude)
        street_ids.append(street_id)
        street_names.append(street_name)
        contexts.append(context)
        persistent_ids.append(persistent_id)
        crime_ids.append(crime_id)
        location_subtypes.append(location_subtype)
        months.append(month)
    
    #Creating a dataframe and using its vectorizaion properties to assign the remaning columns.
    df_final = pd.DataFrame(codes, columns = ["codes"])
    df_final["procedures"] = procedures
    df_final["dates"] = dates
    df_final["person_ids"] = person_ids
    df_final["crime_categories"] = crime_categories
    df_final["location_types"] = location_types
    df_final["latitudes"] = latitudes
    df_final["longitudes"] = longitudes
    df_final["street_ids"] = street_ids
    df_final["street_names"] = street_names
    df_final["contexts"] = contexts 
    df_final["persistent_ids"] = persistent_ids
    df_final["crime_ids"] = crime_ids
    df_final["location_subtypes"] = location_subtypes
    df_final["months"] = months
    #The Dataframe now holds every single entry of our response.
    
    #Converting the Dataframe to a dictionary:
    dictionary = df_final.to_dict(orient = "index")

    #If the second paramter of the function ("n_records") is equal to "None":
    if n_records == "All":
        
        #Return the all the records in dictionary in a json format.
        if csv == "csv":
            df_final.to_csv(f'all_records_during_{my_date}', index=False)
            return "All records have been saved in a .csv format"
        else:
            return jsonify(dictionary)
           
    #Else if the "n_records" is a interger stored as an string and is within the amounts of total records:
    elif int(n_records) in range(len(dictionary)):
        if csv == "csv":
            n_record = int(n_records)
            df_final[:n_record].to_csv(f'{n_record}_records_during_{my_date}',index=False)
            return "All records have been saved in a .csv format"
        else:
            n_record = int(n_records)
            return jsonify(list(itertools.islice(dictionary.items(), 0, n_record)))
    
    #In the case the "n_records" paramter is not "All" or a string stored as an interger that is bigger then then the total amount of records return a suggestion:
    else:
        return '<README>Do Not Panic! Your request has been successful. Unfortunatley the n_records paramter exeeds the amount of records in the dictionary. Try again by using either "All" in your path to retrive all records or inserting the amount of records you want to request.<README>'


@app.route('/api/code_count/<date>', methods = ['GET']) # The "/code_count/<date>" Path calls the function
def get_code(date):#"get_code" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        all_crime_data = resp.json()

    #Else return the "status_code" of the respons:
    else:
        return resp.status_code
    
    #Create an empty list ("location") and an empty dictionary ("consequences"):
    location = []
    consequences = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(all_crime_data)):
        
    #For every single "i" record in the response dictionary:
    
        #1. Take the code value in the category section of the record:
        row = all_crime_data[i]["category"]["code"]
        
        #2. Append the value to the location list:
        location.append(row)
 
        #3. Count the apperance of each entry:
        if row in consequences: 
            consequences[row] = consequences[row] +1 
        else:
            consequences[row] = 1

    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_consequences = pd.DataFrame(list(consequences.items()), columns=['consequence', 'count'])

    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_consequences["percentage"] = df_consequences["count"] / df_consequences["count"].sum()
    
    #Cleaning column font:
    df_consequences["consequence"] = clean_col(df_consequences["consequence"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    consequences_dict = df_consequences.sort_values("percentage", ascending = True).to_dict("index")
  
    #Return the dictionary in json format:
    return jsonify(consequences_dict)


@app.route('/api/code_count/graph/<date>', methods = ['GET']) # The "/code_count/graph/<date>" Path calls the function
@auth.login_required
def get_code_graph(date):#"get_code_graph" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        all_crime_data = resp.json()

    #Else return the "status_code" of the respons:
    else:
        return resp.status_code
    
    #Create an empty list ("location") and an empty dictionary ("consequences"):
    location = []
    consequences = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(all_crime_data)):
        
    #For every single "i" record in the response dictionary:
    
        #1. Take the code value in the category section of the record:
        row = all_crime_data[i]["category"]["code"]
        
        #2. Append the value to the location list:
        location.append(row)
 
        #3. Count the apperance of each entry:
        if row in consequences: 
            consequences[row] = consequences[row] +1 
        else:
            consequences[row] = 1

    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_consequences = pd.DataFrame(list(consequences.items()), columns=['consequence', 'count'])

    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_consequences["percentage"] = df_consequences["count"] / df_consequences["count"].sum()
    
    #Cleaning column font:
    df_consequences["consequence"] = clean_col(df_consequences["consequence"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    consequences_dict = df_consequences.sort_values("percentage", ascending = True).to_dict("index")
  
    #Creating three empty lists to fill with the keys and values of the dictionary:
    counts = []
    percentages = []
    lables = []

    #Running a loop which iterates n_times (n = to the total records in the "loc_dict" dictionary):
    for i in range(len(consequences_dict)):
     
    #For every single "i" record in the dictionary:
    
        #Extract the value from count:
        count = consequences_dict[i]["count"]
        
        #Extract the value from percentage:
        percentage = consequences_dict[i]["percentage"]
        
        #Extract the key from label:
        label = consequences_dict[i]["consequence"]

        #Append the values and keys to their respective list:
        counts.append(count)
        percentages.append(percentage)
        lables.append(label)
    
    #Sign in to my personal Plotly API:
    API_KEY = app.config['MY_API_KEY']
    py.sign_in('kseniyakamen', API_KEY)
    
    #Construct a trace for the Graph where x equal to the "counts" list and y is equal to the "lables" list:
    trace1 = {
              "x": lables, 
              "y": counts, 
              "marker": {
                "color": "rgba(55, 128, 191, 0.6)", 
                "line": {
                  "color": "rgba(55, 128, 191, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Consequences Count During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }
    
    #Construct a trace for the Graph where x equal to the "percentage" list and y is equal to the "lables" list:
    trace2 = {
              "x": lables, 
              "y": percentages, 
              "marker": {
                "color": "rgba(255, 153, 51, 0.6)", 
                "line": {
                  "color": "rgba(255, 153, 51, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Consequences Percentages During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }

    #Inserting the two traces in the an apposite variable called data:
    data = go.Data([trace1, trace2])
    
    #Dictating the layout for the Figure (stacked bar-chart):
    layout = {"barmode": "stack", "title": 'Crime Consequences During {}'.format(my_date)}
    
    #Setting the parameters for the figure:
    fig = go.Figure(data=data, layout=layout)
    
    #Plotting the figure:
    plot_url = py.plot(fig)

    #Return the link of the figure and send the app user directly to the webpage which is hosting the Graphs:
    return jsonify(plot_url)


@app.route('/api/location_count/<date>', methods = ['GET']) #The "/location_count/<date>" Path calls the function
@auth.login_required
def get_loc(date): #"get_loc" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        all_values = resp.json()

    #Else return the "status_code" of the respons:
    else:
        return resp.status_code

    #Create an empty list ("location") and an empty dictionary ("location_type"):
    location = []
    location_type = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(all_values)):
        
    #For every single "i" record in the response dictionary:
    
        #1. Take the location_subtype value in the crime section of the record:
        row = all_values[i]["crime"]["location_subtype"]
         
        #2. Append the value to the location list:
        location.append(row)
        
        #3. Count the apperance of each entry:
        if row in location_type:
            location_type[row] =location_type[row] +1 
        else:
            location_type[row] = 1
    
    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_location = pd.DataFrame(list(location_type.items()), columns=['location', 'count'])
    
    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_location["percentage"] = df_location["count"] / df_location["count"].sum()
    
    #Cleaning column strings:
    df_location["location"] = clean_col(df_location["location"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    loc_dict = df_location.sort_values("percentage", ascending = True).to_dict("index")
    
    #Return the dictionary in json format:
    return jsonify(loc_dict)


@app.route('/api/location_count/graph/<date>', methods = ['GET']) #/location_count/graph/<date>" Path calls the function
@auth.login_required
def get_loc_graph(date): #"get_loc_graph" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        all_values = resp.json()

    #Else return the "status_code" of the respons:
    else:
        return resp.status_code
    
    #Creating an empty list ("location") and an empty dictionary ("location_type"):
    location = []
    location_type = {}
    
   #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(all_values)):

   #For every single "i" record in the response dictionary:
    
        #1. Take the location_subtype value in the crime section of the record:
        row = all_values[i]["crime"]["location_subtype"]
         
        #2. Append the value to the location list:
        location.append(row)
        
        #3. Count the apperance of each entry:
        if row in location_type:
            location_type[row] =location_type[row] +1 
        else:
            location_type[row] = 1
    
    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_location = pd.DataFrame(list(location_type.items()), columns=['location', 'count'])
    
    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_location["percentage"] = df_location["count"] / df_location["count"].sum()
    
    #Cleaning column strings:
    df_location["location"] = clean_col(df_location["location"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    loc_dict = df_location.sort_values("percentage", ascending = True).to_dict("index")
    
    #Creating three empty lists to fill with the keys and values of the dictionary:
    counts = []
    percentages = []
    lables = []

    #Running a loop which iterates n_times (n = to the total records in the "loc_dict" dictionary):
    for i in range(len(loc_dict)):
     
    #For every single "i" record in the dictionary:
    
        #Extract the value from count:
        count = loc_dict[i]["count"]
        
        #Extract the value from percentage:
        percentage = loc_dict[i]["percentage"]
        
        #Extract the key from label:
        label = loc_dict[i]["location"]

        #Append the values and keys to their respective list:
        counts.append(count)
        percentages.append(percentage)
        lables.append(label)
    
    #Sign in to my personal Plotly API:
    API_KEY = app.config['MY_API_KEY']
    py.sign_in('kseniyakamen', API_KEY)
    
    #Construct a trace for the Graph where x equal to the "counts" list and y is equal to the "lables" list:
    trace1 = {
              "x": lables, 
              "y": counts, 
              "marker": {
                "color": "rgba(55, 128, 191, 0.6)", 
                "line": {
                  "color": "rgba(55, 128, 191, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Sub_Location Count During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }
    
    #Construct a trace for the Graph where x equal to the "percentage" list and y is equal to the "lables" list:
    trace2 = {
              "x": lables, 
              "y": percentages, 
              "marker": {
                "color": "rgba(255, 153, 51, 0.6)", 
                "line": {
                  "color": "rgba(255, 153, 51, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Sub_Location Percentages During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }

    #Inserting the two traces in the an apposite variable called data:
    data = go.Data([trace1, trace2])
    
    #Dictating the layout for the Figure (stacked bar-chart):
    layout = {"barmode": "stack", "title": 'Crime Sub_Location During {}'.format(my_date)}
    
    #Setting the parameters for the figure:
    fig = go.Figure(data=data, layout=layout)
    
    #Plotting the figure:
    plot_url = py.plot(fig)

    #Return the link of the figure and send the app user directly to the webpage which is hosting the Graphs:
    return jsonify(plot_url)


@app.route('/api/crime_count/<date>', methods = ['GET']) #/crime_count/<date>" Path calls the function
@auth.login_required
def get_crime(date): #"get_crime" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        dicts = resp.json()

    #Else return the "status_code" of the response:
    else:
        return resp.status_code


    #Create an empty list ("location") and an empty dictionary ("crime_category"):
    location = []
    crime_category = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(dicts)):
        
    #For every single "i" record in the response dictionary:
    
        #1. Take the category value in the crime section of the record:
        row = dicts[i]["crime"]["category"]
        
        #2. Append the value to the location list:
        location.append(row)
        
        #3. Count the apperance of each entry:
        if row in crime_category:
            crime_category[row] = crime_category[row] +1 
        else:
            crime_category[row] = 1
  
    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_crimes = pd.DataFrame(list(crime_category.items()), columns=['crime', 'count'])
    
    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_crimes["percentage"] = df_crimes["count"] / df_crimes["count"].sum()
    
    #Cleaning column strings:
    df_crimes["crime"] = clean_col(df_crimes["crime"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    dict_crimes = df_crimes.sort_values("percentage", ascending = True).to_dict("index")
    
    #Return the dictionary in json format:
    return jsonify(dict_crimes)


@app.route('/api/crime_count/graph/<date>', methods = ['GET']) #/crime_count/graph/<date>" Path calls the function
@auth.login_required
def get_crime_graph(date): #"get_crime_graph" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        dicts = resp.json()

    #Else return the "status_code" of the response:
    else:
        return resp.status_code

    #Creating an empty list ("location") and an empty dictionary ("crime_category"):
    location = []
    crime_category = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(dicts)):
        
    #For every single "i" record in the response dictionary:
        
       #1. Take the category value in the crime section of the record:
        row = dicts[i]["crime"]["category"]
        
        #2. Append the value to the location list:
        location.append(row)
        
        #3. Count the apperance of each entry:
        if row in crime_category:
            crime_category[row] = crime_category[row] +1 
        else:
            crime_category[row] = 1
        
    #Transform the dictionary with the count of the apperances of each entry into a DataFrame:
    df_crimes = pd.DataFrame(list(crime_category.items()), columns=['crime', 'count'])
    
    #Utilise the vectorised functionalities of DataFrames to compute a new percentage column:
    df_crimes["percentage"] = df_crimes["count"] / df_crimes["count"].sum()
    
    #Cleaning column strings:
    df_crimes["crime"] = clean_col(df_crimes["crime"])
    
    #Sort values in aseconding order and convert the new DataFrame back to a dictionary:
    dict_crimes = df_crimes.sort_values("percentage", ascending = True).to_dict("index")
    
    #Creating three empty lists to fill with the keys and values of the dictionary:
    counts = []
    percentages = []
    lables = []

    #Running a loop which iterates n_times (n = to the total records in the "loc_dict" dictionary):
    for i in range(len(dict_crimes)):
     
    #For every single "i" record in the dictionary:
    
        #Extract the value from count:
        count = dict_crimes[i]["count"]
        
        #Extract the value from percentage:
        percentage = dict_crimes[i]["percentage"]
        
        #Extract the key from label:
        label = dict_crimes[i]["crime"]

        #Append the values and keys to their respective list:
        counts.append(count)
        percentages.append(percentage)
        lables.append(label)
    
    #Sign in to my personal Plotly API:
    API_KEY = app.config['MY_API_KEY']
    py.sign_in('kseniyakamen', API_KEY)
    
    #Construct a trace for the Graph where x equal to the "counts" list and y is equal to the "lables" list:
    trace1 = {
              "x": lables, 
              "y": counts, 
              "marker": {
                "color": "rgba(55, 128, 191, 0.6)", 
                "line": {
                  "color": "rgba(55, 128, 191, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Category Count During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }
    
    #Construct a trace for the Graph where x equal to the "percentage" list and y is equal to the "lables" list:
    trace2 = {
              "x": lables, 
              "y": percentages, 
              "marker": {
                "color": "rgba(255, 153, 51, 0.6)", 
                "line": {
                  "color": "rgba(255, 153, 51, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Category Percentages During {}'.format(my_date), 
              "orientation": "v", 
              "type": "bar"
            }

    #Inserting the two traces in the an apposite variable called data:
    data = go.Data([trace1, trace2])
    
    #Dictating the layout for the Figure (stacked bar-chart):
    layout = {"barmode": "stack", "title": 'Crime Category During {}'.format(my_date)}
    
    #Setting the parameters for the figure:
    fig = go.Figure(data=data, layout=layout)
    
    #Plotting the figure:
    plot_url = py.plot(fig)

    #Return the link of the figure and send the app user directly to the webpage which is hosting the Graphs:
    return jsonify(plot_url)
    

@app.route('/api/all_graphs/<date>', methods = ['GET']) #"/all_graphs/<date>" Path calls the function
@auth.login_required
def get_graphs(date): #"get_graphs" has only one paramter ("date") which is given in the path.
    
    #Setting the API url:
    crime_url_template = 'https://data.police.uk/api/outcomes-at-location?lat={lat}&lng={lng}&date={data}'

    my_latitude = '51.509865' #The latitude of London City
    my_longitude = '-0.118092' #The longitute of London City
    extract_date = str(date) #Converting the "date" parameter given by the path to a string
    year = extract_date[0:4] #Slicing date in "year" (ex. "2018")
    month = extract_date[4:len(extract_date)] #Slicing date in "month" (ex. "11")
    my_date = year + "-" + month #Connecting "year" and "month" whilst adding a dash (ex. "2018-11")
   
    #Calling format on the API string to change {lat}, {lng}, {data} into the above-set paramters:
    crime_url = crime_url_template.format(
        lat = my_latitude,
        lng = my_longitude,
        data = my_date) 

    #Calling ".get" function to establish a connection with the Police API:
    resp = requests.get(crime_url)
    
    #If a "status_code" equal to 200 is returned then the resp in "json" format is returned:
    if resp.status_code == 200:
        dicts = resp.json()

    #Else return the "status_code" of the response:
    else:
        return resp.status_code
    
    

    #Creating an empty list ("loc") and an empty dictionary ("location_type"):
    loc = []
    location_type = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(dicts)):
        
     #For every single "i" record in the response dictionary:
    
        #1. Take the location_subtype value in the crime section of the record:
        row = dicts[i]["crime"]["location_subtype"]
        
        #2. Clean each value
        row = row.strip()
        row = row.lower()
        row = row.replace(" ", "_")
        row = row.replace("(", "")
        row = row.replace(")", "")
        row = row.strip()
         
        #3. Append the value to the location list:
        loc.append(row)
        
        #4. Count the apperance of each entry:
        if row in location_type:
            location_type[row] = location_type[row] +1 
        else:
            location_type[row] = 1
    
    #Creating an empty list ("location") and an empty dictionary ("crime_category"):
    location = []
    crime_category = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(dicts)):
    
    #For every single "i" record in the response dictionary:
    
        #1. Take the category value in the crime section of the record:
        row = dicts[i]["crime"]["category"]
        
        #2. Clean each value
        row = row.strip()
        row = row.lower()
        row = row.replace(" ", "_")
        row = row.replace("(", "")
        row = row.replace(")", "")
        row = row.strip()
        
        #3. Append the value to the location list:
        location.append(row)
        
        #4. Count the apperance of each entry:
        if row in crime_category:
            crime_category[row] = crime_category[row] +1 
        else:
            crime_category[row] = 1
    
    #Creating an empty list ("locs") and an empty dictionary ("consequences"):
    location = []
    consequences = {}
    
    #Running a loop which iterates n_times (n = to the total records in the response dictionary):
    for i in range(len(dicts)):
    
    #For every single "i" record in the response dictionary:
    
        #1. Take the category value in the crime section of the record:
        row = dicts[i]["category"]["code"]
        
        #2. Clean each value
        row = row.strip()
        row = row.lower()
        row = row.replace(" ", "_")
        row = row.replace("(", "")
        row = row.replace(")", "")
        row = row.strip()
        
        #3. Append the value to the location list:
        location.append(row)
        
        #4. Count the apperance of each entry:
        if row in consequences:
            consequences[row] =consequences[row] +1 
        else:
            consequences[row] = 1        
    
    #Sign in to my personal Plotly API:
    API_KEY = app.config['MY_API_KEY']
    py.sign_in('kseniyakamen', API_KEY)
    
    #Construct a trace for the Graph where x equal to the values in "location_type" and y is equal to the "lables" list:
    trace1 = {
              "x": list(location_type.keys()), 
              "y": list(location_type.values()), 
              "marker": {
                "color": "rgba(55, 128, 191, 0.6)", 
                "line": {
                  "color": "rgba(55, 128, 191, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Sub_Location Count During {}'.format(my_date), 
              "orientation":"v",
              "type": "bar"
            }
    
    #Construct a trace for the Graph where x equal to the values in "crime_category" and y is equal to the "lables" list:
    trace2 = {
              "x": list(crime_category.keys()), 
              "y": list(crime_category.values()), 
              "marker": {
                "color": "rgba(255, 0, 0, 0.6)", 
                "line": {
                  "color": "rgba(255, 0, 0, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Crime_Category Count During {}'.format(my_date), 
              "orientation":"v",
              "type": "bar"
            }
    #Construct a trace for the Graph where x equal to the values in "consequences" and y is equal to the "lables" list:
    trace3 = {
              "x": list(consequences.keys()), 
              "y": list(consequences.values()), 
              "marker": {
                "color": "rgba(255, 153, 51, 0.6)", 
                "line": {
                  "color": "rgba(255, 153, 51, 1.0)", 
                  "width": 1
                }
              }, 
              "name": 'Crime Consequences Count During {}'.format(my_date), 
              "orientation":"v",
              "type": "bar"
            }

    #Inserting the two traces in the an apposite variable called data:
    data = go.Data([trace1, trace2, trace3])
    
    #Dictating the layout for the Figure (stacked bar-chart):
    layout = {"title": 'Crime All Stats During {}'.format(my_date)}
    
    #Setting the parameters for the figure:
    fig = go.Figure(data=data, layout=layout)
    
    #Plotting the figure:
    plot_url = py.plot(fig)

    #Return the link of the figure and send the app user directly to the webpage which is hosting the Graphs:
    return jsonify(plot_url)
    
if __name__ == '__main__':
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(port = 8080,debug=True)