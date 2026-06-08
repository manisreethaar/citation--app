# Auto-Citer — Automatic Reference Citation Tool

**Auto-Citer** scans your academic document, matches author mentions in the body text to the reference list, and inserts properly formatted inline citations — all automatically.

## ✨ Features

- **6 citation styles**: APA 7th, Vancouver, IEEE, Nature/Cell, MLA 9th, Chicago 17th
- **3 file formats**: `.docx` (Word), `.pdf`, `.txt`
- **Smart matching**: Handles `Smith et al. (2020)`, `Smith (2020)`, `Smith and Jones (2018)`, and loose surname-only matches
- **CLI + Web UI**: Use from the command line or via a browser
- **Vercel-ready**: Deployable as a serverless Python app

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the web UI

```bash
python app.py
# Open http://localhost:5000
```

### 3. Or use the CLI

```bash
python auto_citer.py --input paper.docx --style apa
python auto_citer.py --input paper.pdf  --style vancouver --output cited_paper.pdf
python auto_citer.py --input paper.docx --style ieee --report
python auto_citer.py --input paper.txt  --style nature
python auto_citer.py --input paper.docx --style mla
python auto_citer.py --input paper.docx --style chicago
```

---

## 📋 Supported Citation Styles

| Style      | Inline Format          | Field              |
|------------|------------------------|--------------------|
| APA 7th    | `(Smith et al., 2020)` | Social sciences    |
| Vancouver  | `[1]`, `[2]`           | Biomedical         |
| IEEE       | `[1]`, `[2]`           | Engineering / CS   |
| Nature     | `[1]` / superscript    | High-impact science|
| MLA 9th    | `(Smith 42)`           | Humanities         |
| Chicago 17 | `(Smith 2020)`         | History / Arts     |

---

## 📄 Document Format Requirements

Your document **must** end with a reference section headed by one of these headings (case-insensitive):

```
References
Bibliography
Works Cited
Literature Cited
Citations
Sources
```

**Example structure:**
```
... body of the paper where Smith et al. (2020) discuss findings ...

References
Smith, J., Jones, A., & Brown, B. (2020). A great study. Journal of Science, 10(2), 1–5.
Jones, A. (2019). Another paper. Nature, 5, 10–15.
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```env
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=0
```

Generate a secure key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🧪 Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## 🌐 Deploying to Vercel

The repo includes a `vercel.json` for serverless deployment.

```bash
vercel deploy
```

Set the `SECRET_KEY` environment variable in your Vercel project settings.

---

## 📁 Project Structure

```
auto_citer.py        Main pipeline (CLI + importable API)
app.py               Flask web server
citation_styles.py   APA / Vancouver / IEEE / Nature / MLA / Chicago formatting
matcher.py           Regex-based author mention detection
reference_parser.py  Reference section splitter and parser
file_handlers.py     DOCX / PDF / TXT read-write handlers
requirements.txt     Python dependencies
vercel.json          Vercel deployment configuration
tests/               Unit tests
```

---

## 🛠️ CLI Options

| Flag        | Description                                      |
|-------------|--------------------------------------------------|
| `--input`   | Path to input document (required)                |
| `--style`   | Citation style: apa / vancouver / ieee / nature / mla / chicago |
| `--output`  | Output file path (default: `<input>_cited.<ext>`)|
| `--report`  | Print a match report after processing            |
