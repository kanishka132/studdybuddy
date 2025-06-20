import os
import re
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from supabase import create_client
from PyPDF2 import PdfReader
import google.generativeai as genai

# === Load Environment Variables ===
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# === Configure Gemini Model ===
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# === Initialize Supabase ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Flask App Setup ===
app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# === Helper Functions ===
def extract_text_from_supabase_paths(file_paths):
    all_text = ""
    for path in file_paths:
        pdf_bytes = supabase.storage.from_("materials").download(path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            reader = PdfReader(tmp.name)
            all_text += "\n".join([page.extract_text() or "" for page in reader.pages])
    return re.sub(r'\s+', ' ', all_text).strip()

def generate_ai_response(task, text, count=5):
    if task == "summarize":
        prompt = f"Please summarize the following content clearly and concisely:\n{text}"
    elif task == "quiz":
        prompt = f"""
        Create {count} multiple-choice questions based on the text below.
        Each should have 4 options (A, B, C, D) with one correct answer. Return JSON array:
        [
          {{
            "question": "...",
            "options": ["A", "B", "C", "D"],
            "correct_answer": 1
          }}
        ]\nText:\n{text}"""
    elif task == "flashcards":
        prompt = f"""
        Create {count} flashcards from the following text in JSON format:
        [
          {{
            "front": "Term or Question",
            "back": "Answer or Explanation"
          }}
        ]\nText:\n{text}"""
    else:
        return None

    response = model.generate_content(prompt)
    return response.text

# === Routes ===
@app.route("/generate-learning-content", methods=["POST"])
def generate_learning_content():
    try:
        data = request.get_json()
        file_paths = data.get("file_paths", [])
        actions = data.get("actions", [])
        project_name = data.get("project_name", "Untitled Project")

        text = extract_text_from_supabase_paths(file_paths)

        results = {}
        if "summarize" in actions:
            results["summary"] = generate_ai_response("summarize", text)
        if "quiz" in actions:
            results["quiz"] = generate_ai_response("quiz", text)
        if "flashcards" in actions:
            results["flashcards"] = generate_ai_response("flashcards", text)

        return jsonify({
            "success": True,
            "project_name": project_name,
            "results": results
        })

    except Exception as e:
        print("Error in /generate-learning-content:", str(e))
        return jsonify({"success": False, "error": "Processing failed"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})

# === Run App ===
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
