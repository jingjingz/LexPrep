# LexPrep

A lightweight Streamlit application that turns Word (.docx) templates with `` tokens into fill‑able web forms and auto‑generates fully–populated **DOCX** and **RTF** documents.

---

## ✨ Key Features

| Feature           | Details                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Auto‑manifest** | Upload a DOCX with `{{ tokens }}` – the app scans the file, builds a draft JSON manifest, and lets you tweak it before saving the template. |
| **Repeat groups** | Use `root[].field` syntax (e.g. `{{ plaintiffs[].name }}`) to indicate a repeating block.                                                   |
| **Document Name** | Optional input when filling a case; drives download filenames and shows up in history.                                                      |
| **DOCX ➜ RTF**    | Uses LibreOffice (preferred) or Pandoc to convert the filled DOCX to RTF.                                                                   |
| **History**       | Every generated case is stored in SQLite; download past DOCX/RTF anytime.                                                                   |
| **Clean UI**      | Pill‑style sidebar navigation, auto‑styled form labels, drag‑and‑drop uploader.                                                             |

---

## 📂 Project Structure

```text
root/
├─ app.py          # Streamlit front‑end
├─ db.py           # SQLite helpers (templates & cases)
├─ renderer.py     # DOCX fill + RTF conversion
├─ utils.py        # Placeholder extraction from DOCX
├─ data/
│  └─ templates/   # Uploaded template files
├─ outputs/        # Generated docx/rtf files
└─ requirements.txt
```

---

## 🛠️ Installation

```bash
# clone repo
$ git clone https://github.com/your‑org/lexprep.git
$ cd lexprep

# create & activate virtual environment
$ python3 -m venv .venv
$ source .venv/bin/activate   # Windows: .venv\Scripts\Activate

# install python dependencies
$ pip install -r requirements.txt
```

### External dependencies

| Dependency                  | Why                                                  | Install Command                                                                                                                      |
| --------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **LibreOffice** (preferred) | Highest‑fidelity DOCX → RTF conversion               | macOS `brew install --cask libreoffice`  ·  Ubuntu `sudo apt install libreoffice-core`  ·  Windows installer + add `soffice` to PATH |
| **Pandoc** (fallback)       | Simpler, but skips text‑boxes & headers in some docs | macOS `brew install pandoc` · Ubuntu `sudo apt install pandoc` · Windows `choco install pandoc`                                      |

> The app will try LibreOffice first. If `soffice` is not on the `PATH`, it will fall back to Pandoc.

---

## 🚀 Running the App

```bash
$ streamlit run app.py
```

- Open the provided URL (default [http://localhost:8501](http://localhost:8501)).
- **Sidebar → Create Template** to upload your first DOCX template.
- **Sidebar → Create Case / Fill Form** to generate documents.
- **Sidebar → Generated Documents** to view & download past cases.

---

## 🖋️ Placeholder Syntax

| Pattern               | Meaning                                                                                              |
| --------------------- | ---------------------------------------------------------------------------------------------------- |
| `{{ field_name }}`    | Single value. Appears as a text input in the form.                                                   |
| `{{ group[].field }}` | Marks `group` as a repeat section. The form lets the user specify how many repeating items to enter. |

> All braces **must** be plain text in the Word file (not inside content controls).

---

## 💾 Database Schema (SQLite)

### `templates` table

| Column         | Type       | Notes                     |
| -------------- | ---------- | ------------------------- |
| id             | INTEGER PK |                           |
| name           | TEXT       |                           |
| description    | TEXT       |                           |
| manifest\_json | TEXT       | Auto/edited JSON manifest |
| docx\_path     | TEXT       | Stored template file      |
| created\_at    | DATETIME   |                           |

### `cases` table

| Column       | Type              | Notes                          |
| ------------ | ----------------- | ------------------------------ |
| id           | INTEGER PK        |                                |
| doc\_name    | TEXT              | User‑supplied title (optional) |
| template\_id | FK → templates.id |                                |
| input\_json  | TEXT              | Saved form data                |
| docx\_path   | TEXT              | Generated file                 |
| rtf\_path    | TEXT              | Generated file                 |
| created\_at  | DATETIME          |                                |

---

## 🧩 Extending LexPrep

- **Field types** – Currently only `text` & `textarea` are supported. Add more (e.g. `date`) by updating `render_fields()` and the manifest generator.
- **Auth** – Integrate Streamlit’s experimental auth or wrap behind a proxy for protected deployments.
- **Styling** – Adjust CSS in `app.py` or use Streamlit‑Extras components for richer UI.

---

## 📜 License

[MIT](LICENSE)

---

## 🙏 Acknowledgements

- Streamlit – UI framework
- python‑docx & docxtpl – DOCX parsing & templating
- LibreOffice & Pandoc – document conversion

