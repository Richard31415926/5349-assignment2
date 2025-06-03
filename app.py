import boto3
import json
import mysql.connector
from flask import Flask, request, render_template
from werkzeug.utils import secure_filename
from io import BytesIO
import os

app = Flask(__name__)

# S3 Configuration
S3_BUCKET = "my-assignment2-bucket-540979776"
S3_REGION = "us-east-1"

def get_s3_client():
    return boto3.client("s3", region_name=S3_REGION)

# RDS Configuration (get from Secrets Manager)
def get_db_secret():
    secret_name = "my-assignment2-db-secret"
    region_name = "us-east-1"
    client = boto3.client('secretsmanager', region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    return secret

def get_db_connection():
    secret = get_db_secret()
    connection = mysql.connector.connect(
        host=secret['host'],
        user=secret['username'],
        password=secret['password'],
        database=secret['dbname']
    )
    return connection

# Allowed file types
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def upload_form():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return render_template("upload.html", error="No file selected")

    file = request.files["file"]

    if file.filename == "":
        return render_template("upload.html", error="No file selected")

    if not allowed_file(file.filename):
        return render_template("upload.html", error="Invalid file type")

    filename = secure_filename(file.filename)
    file_data = file.read()
    
    #Add uploads/ prefix to the S3 key
    key = f"uploads/{filename}"

    try:
        s3 = get_s3_client()
        s3.upload_fileobj(BytesIO(file_data), S3_BUCKET, key)
    except Exception as e:
        return render_template("upload.html", error=f"S3 Upload Error: {str(e)}")

    # Generate public or presigned file URL
    file_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    return render_template("upload.html", file_url=file_url, message="File uploaded successfully!")

@app.route("/gallery")
def gallery():
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT image_key, caption FROM captions ORDER BY uploaded_at DESC")
        results = cursor.fetchall()
        connection.close()

        images_with_captions = [
            {
                "url": get_s3_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": row["image_key"]},
                    ExpiresIn=3600
                ),
                "caption": row["caption"],
            }
            for row in results
        ]

        return render_template("gallery.html", images=images_with_captions)

    except Exception as e:
        return render_template("gallery.html", error=f"Database Error: {str(e)}")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
