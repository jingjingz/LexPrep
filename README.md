# LexPrep

A lightweight **Streamlit** application that turns Word (`.docx`) templates containing `{{ tokens }}` into fill‑able web forms and auto‑generates populated **DOCX** and **RTF** files.

---

## ✨ Key Features

| Feature                         | Details                                                                                                                          |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Zero‑config forms**           | Upload a DOCX with `{{ tokens }}` – the app scans the file, builds a draft JSON manifest, and lets you tweak it before saving.   |
| **Repeat groups**               | Use `root[].field` syntax (e.g. `{{ plaintiffs[].name }}`) to mark repeating blocks.                                             |
| **Built‑in & custom templates** | Ships with ready‑made templates in ``; users can upload their own which are stored in `` at runtime.                             |
| **DOCX ➜ RTF**                  | Converts with **Pandoc** by default; if `soffice` (LibreOffice) is on the system the app will fall back to it when Pandoc fails. |
| **History & download**          | Every generated case is stored in SQLite; past DOCX/RTF can be re‑downloaded.                                                    |
| **Theme matching**              | Uses a project‑level `` so the blue primary color is identical locally and in the cloud.                                         |

---

## 📂 Project Structure

```text
root/
├─ app.py                # Streamlit UI
├─ db.py                 # SQLite helpers (templates & cases)
├─ renderer.py           # DOCX fill + RTF conversion (Pandoc first, LibreOffice optional)
├─ utils.py              # Placeholder extraction from DOCX
├─ default_templates/    # Read‑only templates that ship with the repo
├─ data/
│  └─ templates/         # User‑uploaded templates (ephemeral in cloud)
├─ .streamlit/
│  └─ config.toml        # Theme (Columbia blue primaryColor)
├─ requirements.txt      # Python deps (pinned)
├─ packages.txt          # "apt" deps – **pandoc** only
└─ README.md
```

---

## 🛠️ Installation (Local Dev)

```bash
# clone repo
$ git clone https://github.com/your‑org/lexprep.git
$ cd lexprep

# create & activate virtual environment
$ python3 -m venv .venv        # or conda create -n lexprep python=3.10
$ source .venv/bin/activate    # Windows: .venv\Scripts\activate

# install Python requirements
$ pip install -r requirements.txt
```

### External / System Dependencies

| Package                    | Why                                | Install Command (examples)                                                           |
| -------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------ |
| **Pandoc** (required)      | DOCX → RTF conversion              | macOS `brew install pandoc` · Ubuntu `sudo apt install pandoc`                       |
| **LibreOffice** (optional) | Higher‑fidelity fallback converter | macOS `brew install --cask libreoffice` · Ubuntu `sudo apt install libreoffice-core` |

> **Runtime logic:** The app tries **Pandoc** first. If Pandoc raises an error **and** `soffice` is on the `PATH`, it falls back to LibreOffice. On Streamlit Cloud LibreOffice is *not* installed, so Pandoc must succeed.

---

## 🚀 Running the App Locally

```bash
$ streamlit run app.py
```

Open the given URL (default [http://localhost:8501](http://localhost:8501)).

---

## ☁️ One‑Click Deployment to Streamlit Community Cloud

1. **Fork** or grant access to this repo.
2. Push any changes – make sure `` and `` are committed.
   - `packages.txt` contains just one line: `pandoc`.
3. Log in to [https://share.streamlit.io](https://share.streamlit.io), click **New app** → *From existing repo*.
4. Fill in:
   - **Repo**: `your‑org/lexprep`
   - **Branch**: `main` (or whichever you deploy)
   - **Main file**: `app.py`
5. Click **Deploy**.

The container installs Pandoc via `apt`, builds Python wheels from `requirements.txt`, then runs the app.  Subsequent `git push` events trigger automatic rebuilds.

### Custom URL

In the Cloud dashboard → **Settings** → **General → Custom sub‑domain**, pick a unique slug (e.g. `lexprep`) to get [https://lexprep.streamlit.app](https://lexprep.streamlit.app).

### Persistence Caveat

*Files saved in **`data/templates/`** survive routine reruns but disappear when the container rebuilds (every new commit or occasional maintenance).  For durable storage plug in S3 / Supabase or another external bucket.*

---

## 🖋️ Placeholder Syntax (Cheat Sheet)

| Pattern               | Meaning                                      |
| --------------------- | -------------------------------------------- |
| `{{ field }}`         | Single text input.                           |
| `{{ group[].field }}` | Repeating block; user chooses how many rows. |

All braces must be plain text (not in content‑controls).

---

## 💾 Database Schema

### `templates`

| Column         | Type       | Notes                |
| -------------- | ---------- | -------------------- |
| id             | INTEGER PK |                      |
| name           | TEXT       | Display name         |
| manifest\_json | TEXT       | Form blueprint       |
| docx\_path     | TEXT       | Stored template file |
| created\_at    | DATETIME   |                      |

### `cases`

| Column       | Type       | Notes                          |
| ------------ | ---------- | ------------------------------ |
| id           | INTEGER PK |                                |
| doc\_name    | TEXT       | User‑supplied label (optional) |
| template\_id | INTEGER FK | References `templates.id`      |
| input\_json  | TEXT       | Saved form data                |
| docx\_path   | TEXT       | Generated DOCX                 |
| rtf\_path    | TEXT       | Generated RTF                  |
| created\_at  | DATETIME   |                                |

---

## 🔧 Extending LexPrep

- **Field widgets** – add new types (dates, checkboxes…) in `render_fields()` + manifest generator.
- **Authentication** – wrap behind a proxy or integrate Streamlit’s new auth hooks.
- **Persistent storage** – swap `data/templates/` for S3, Supabase Storage, etc.

---

## 📜 License

[MIT](LICENSE)

---

## 🙏 Acknowledgements

- [Streamlit](https://streamlit.io) – UI framework
- [python‑docx](https://python-docx.readthedocs.io/) & [docxtpl](https://docxtpl.readthedocs.io/) – DOCX parsing & templating
- [Pandoc](https://pandoc.org) & [LibreOffice](https://www.libreoffice.org/) – document conversion
- [Mango](https://freeimage.host/i/FvE74Tl) - The cat

