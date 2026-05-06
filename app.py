from flask import Flask, request, jsonify, render_template
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

print("Cargando modelo...")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2-0.5B-Instruct")
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2-0.5B-Instruct", dtype=torch.float32)
model.eval()
print("Modelo listo.")

MAX_CHARS = 2500


def extract_text(content, filename):
    if filename.lower().endswith((".htm", ".html")):
        soup = BeautifulSoup(content, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    return content


def detect_sections(text):
    pattern = re.compile(r"(Item\s+\d+[A-Za-z]?[\.\—\-]?\s{0,4}[A-Z][^\n]{3,60})", re.IGNORECASE)
    matches = list(pattern.finditer(text))

    sections = []
    for i, match in enumerate(matches):
        name = re.sub(r"\s+", " ", match.group()).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if len(body) > 100:
            sections.append({"name": name[:80], "text": body[:MAX_CHARS]})

    if not sections:
        sections.append({"name": "Documento completo", "text": text[:MAX_CHARS]})

    return sections


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No se recibió archivo"}), 400

    content = file.read().decode("utf-8", errors="ignore")
    text = extract_text(content, file.filename)
    sections = detect_sections(text)
    return jsonify({"sections": sections})


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    text = data.get("text", "")[:MAX_CHARS]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial analyst specialized in SEC filings. "
                "Analyze the sentiment of the given text excerpt. "
                "Reply in this exact format:\n"
                "Sentiment: <Positive|Negative|Neutral>\n"
                "Reason: <one sentence explaining why>"
            ),
        },
        {"role": "user", "content": text},
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([prompt], return_tensors="pt")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=120,
            pad_token_id=tokenizer.eos_token_id,
        )

    result = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    sentiment = "Neutral"
    if re.search(r"sentiment:\s*positive", result, re.IGNORECASE):
        sentiment = "Positive"
    elif re.search(r"sentiment:\s*negative", result, re.IGNORECASE):
        sentiment = "Negative"

    return jsonify({"sentiment": sentiment, "explanation": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=False)
