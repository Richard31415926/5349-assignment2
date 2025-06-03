"""
COMP5349 Assignment: Image Captioning App using Gemini API and AWS Services

IMPORTANT:
Before running this application, ensure that you update the following configurations:
1. Replace the GEMINI API key (`GOOGLE_API_KEY`) with your own key from Google AI Studio.
2. Replace the AWS S3 bucket name (`S3_BUCKET`) with your own S3 bucket.
3. Update the RDS MySQL database credentials (`DB_HOST`, `DB_USER`, `DB_PASSWORD`).
4. Ensure all necessary dependencies are installed by running the provided setup script.

Failure to update these values will result in authentication errors or failure to access cloud services.
"""

# To use on an AWS Linux instance
# #!/bin/bash
# sudo yum install python3-pip -y
# pip install flask
# pip install mysql-connector-python
# pip install -q -U google-generativeai
# pip install boto3 werkzeug
# sudo yum install -y mariadb105

import boto3  # AWS S3 SDK
import json
import mysql.connector  # MySQL database connector
from flask import Flask, request, render_template, jsonify  # Web framework
from werkzeug.utils import secure_filename  # Secure filename handling
import google.generativeai as genai  # Gemini API for image captioning
import base64  # Encoding image data for API processing
from io import BytesIO  # Handling in-memory file objects
from PIL import Image

# Configure Gemini API, REPLACE with your Gemini API key
GOOGLE_API_KEY = "AIzaSyAx7QT2mKIJbDtAPGrY9bsKXwlEfDvjiAw"
genai.configure(api_key=GOOGLE_API_KEY)

# Choose a Gemini model for generating captions
model = genai.GenerativeModel(model_name="gemini-2.0-pro-exp-02-05")

def generate_image_caption(image_data):
    """
    Generate a caption for an uploaded image using the Gemini API.

    :param image_data: Raw binary image data
    :return: Generated caption or error message
    """
    try:
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        response = model.generate_content(
            [
                {"mime_type": "image/jpeg", "data": encoded_image},
                "Caption this image.",
            ]
        )
        return response.text if response.text else "No caption generated."
    except Exception as e:
        return f"Error: {str(e)}"

# Flask app setup
app = Flask(__name__)

# AWS S3 Configuration, REPLACE with your S3 bucket
S3_BUCKET = "my-assignment2-bucket-540979776"
S3_REGION = "us-east-1"


def get_s3_client():
    """Returns a new S3 client that automatically refreshes credentials if using an IAM role."""
    return boto3.client("s3", region_name=S3_REGION)

# Database Configuration, REPLACE with your RDS credentials
DB_HOST = "my-assignment2-db.c6zsj2nigeuf.us-east-1.rds.amazonaws.com"
DB_NAME = "my-assignment2-db"
DB_USER = "admin"
DB_PASSWORD = "13792279858"

def get_db_connection():
    """
    Establishes a connection to the MySQL RDS database.

    :return: Database connection object or None if connection fails
    """
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
        return connection
    except mysql.connector.Error as err:
        print("Error connecting to database:", err)
        return None

# Allowed file types for upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    """
    Checks if the uploaded file has a valid extension.

    :param filename: Name of the uploaded file
    :return: True if valid, False otherwise
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def upload_form():
    """Render the homepage with the file upload form."""
    return render_template("index.html")

@app.route("/upload", methods=["GET", "POST"])
def upload_image():
    """
    Handles image upload, stores the file in AWS S3,
    generates a caption using Gemini API, and saves metadata in MySQL RDS.
    """
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("upload.html", error="No file selected")

        file = request.files["file"]

        if file.filename == "":
            return render_template("upload.html", error="No file selected")

        if not allowed_file(file.filename):
            return render_template("upload.html", error="Invalid file type")

        filename = secure_filename(file.filename)
        file_data = file.read()  # Read file as binary

        # Upload file to S3
        try:
            s3 = get_s3_client()  # Get a fresh S3 client
            s3.upload_fileobj(BytesIO(file_data), S3_BUCKET, filename)
        except Exception as e:
            return render_template("upload.html", error=f"S3 Upload Error: {str(e)}")
        '''
        # Generate and upload thumbnail
        try:
            thumb_data = generate_thumbnail(file_data)
            s3.upload_fileobj(thumb_data, S3_BUCKET, f"thumbnails/{filename}")
        except Exception as e:
            return render_template("upload.html", error=f"Thumbnail Upload Error: {str(e)}")

        # Generate caption
        caption = generate_image_caption(file_data)

        # Save metadata to the database
        try:
            connection = get_db_connection()
            if connection is None:
                return render_template("upload.html", error="Database Error: Unable to connect to the database.")
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO captions (image_key, caption) VALUES (%s, %s)",
                (filename, caption),
            )
            connection.commit()
            connection.close()
        except Exception as e:
            return render_template("upload.html", error=f"Database Error: {str(e)}")
        '''
        # Prepare image for frontend display using Base64 encoding
        encoded_image = base64.b64encode(file_data).decode("utf-8")
        file_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        
        return render_template("upload.html", image_data=encoded_image, file_url=file_url, caption=caption)

    return render_template("upload.html")
    

@app.route("/gallery")
def gallery():
    """
    Retrieves images and their captions from the database,
    generates pre-signed URLs for secure access, and renders the gallery page.
    """
    try:
        connection = get_db_connection()
        if connection is None:
            return render_template("gallery.html", error="Database Error: Unable to connect to the database.")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT image_key, caption FROM captions ORDER BY uploaded_at DESC")
        results = cursor.fetchall()
        connection.close()

        images_with_captions = [
            {
                "url": get_s3_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": row["image_key"]},
                    ExpiresIn=3600,  # URL expires in 1 hour
                ),
                "caption": row["caption"],
            }
            for row in results
        ]

        return render_template("gallery.html", images=images_with_captions)

    except Exception as e:
        return render_template("gallery.html", error=f"Database Error: {str(e)}")

def generate_thumbnail(file_data):
    image = Image.open(BytesIO(file_data))
    image.thumbnail((128, 128))  
    thumb_io = BytesIO()
    image.save(thumb_io, format='JPEG')
    thumb_io.seek(0)
    return thumb_io

def get_db_secret():
    secret_name = "my-assignment2-db-secret"
    region_name = "us-east-1"
    client = boto3.client('secretsmanager', region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=80)
