
import boto3
import json
import mysql.connector
from flask import Flask, request, render_template
from werkzeug.utils import secure_filename
from io import BytesIO
import os
import time
import base64

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
    key = f"uploads/{filename}"

    try:
        s3 = get_s3_client()
        s3.upload_fileobj(BytesIO(file_data), S3_BUCKET, key)
    except Exception as e:
        return render_template("upload.html", error=f"S3 Upload Error: {str(e)}")

    # Wait for Lambda-generated caption to appear in the DB
    caption = "Waiting for caption..."
    timeout = 10
    elapsed = 0
    interval = 1

    while elapsed < timeout:
        try:
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT caption FROM captions WHERE image_key = %s", (key,))
            result = cur.fetchone()
            conn.close()
            if result and result["caption"]:
                caption = result["caption"]
                break
        except Exception as e:
            print("DB Error:", e)
            break

        time.sleep(interval)
        elapsed += interval

    encoded_image = base64.b64encode(file_data).decode("utf-8")
    file_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    return render_template("upload.html", image_data=encoded_image, file_url=file_url, caption=caption)

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
