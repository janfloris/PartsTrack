# PartsTrack

PartsTrack is a web application for tracking parts ordered for
dealership work items and monitoring receiving progress.

## Features

-   Track Work Items such as Work Orders, Estimates, Invoices, and
    Quotes.
-   Organize supplier orders under each Work Item.
-   Record part numbers, descriptions, quantities ordered, quantities
    received, and notes.
-   Update and edit parts and supplier orders.
-   Monitor receiving progress with status indicators:
    -   **Red --- Not Received:** no parts have been received, or no
        parts have been ordered.
    -   **Yellow --- Partially Received:** some, but not all, ordered
        parts have been received.
    -   **Green --- Fully Received:** all ordered quantities have been
        received.
-   Search active Work Items by Work Item number, customer, technician,
    or type.
-   Filter the dashboard by receiving status.
-   Archive Work Items and restore them later.
-   Store application data in a local SQLite database.

## Technology

-   Python
-   Flask
-   Flask-SQLAlchemy
-   SQLite
-   Bootstrap 5

## Project Structure

``` text
PartsTrack/
├── app/
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── new_work_item.html
│   │   ├── work_item_details.html
│   │   ├── edit_part.html
│   │   ├── edit_parts_order.html
│   │   └── archive.html
│   └── static/
│       └── css/
│           └── style.css
├── config.py
├── run.py
└── partstrack.db
```

The SQLite database file is local to the application. Do not commit a
database containing customer or dealership information to a public
repository.

## Setup on Windows

### 1. Install Python

Install a supported version of Python for Windows. During installation,
enable **Add Python to PATH**.

### 2. Open the project

Open the PartsTrack folder in Visual Studio Code.

### 3. Create and activate a virtual environment

In the VS Code terminal, run:

``` powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents activation, you may need to adjust the execution
policy for your user or activate the environment using the VS Code
interpreter selection.

### 4. Install dependencies

``` powershell
python -m pip install Flask Flask-SQLAlchemy Flask-Login
```

If the project has a `requirements.txt` file, install from it instead:

``` powershell
python -m pip install -r requirements.txt
```

### 5. Run PartsTrack

``` powershell
python run.py
```

Open the local address shown in the terminal in your browser. The exact
address depends on the Flask configuration.

## Database

PartsTrack uses SQLite through Flask-SQLAlchemy. The database stores
Work Items, supplier orders, and part lines.

Keep your local database backed up. If you are using real dealership
data, protect the database file and avoid sharing it in GitHub.

## GitHub Notes

Before pushing the project to GitHub:

-   Do not commit `partstrack.db` if it contains real or sensitive data.
-   Do not commit your virtual environment (`.venv`).
-   Do not commit secret keys or credentials.
-   Consider adding a `.gitignore` file for local and generated files.

## Current Status

PartsTrack is an actively developed project. Features and setup details
may change as development continues.
