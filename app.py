from flask import Flask, request, render_template, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv



# Load environment variables from .env file (if present)
load_dotenv()

# Flask Application Setup
app = Flask(__name__)
app.secret_key = "your_secret_key"  # Replace with a secure secret key
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Create uploads folder if it doesn't exist
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# SQLAlchemy Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "postgresql://autohive_user:uEGA0sF07nf7L0PDFaBOwomlkuPMeqCT@dpg-ctmnsea3esus739r3m30-a.oregon-postgres.render.com/autohive_db"
)  # Read from environment variable or fallback to hardcoded URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize SQLAlchemy and Flask-Migrate
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Set up logging
handler = RotatingFileHandler('activity.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


def log_activity(employee, action, details, company_id=None):
    """
    Logs an activity to the ActivityLog table.
    :param employee: Name of the employee performing the action.
    :param action: Action performed (e.g., 'Updated Contact Info').
    :param details: Details about the action.
    :param company_id: (Optional) ID of the company related to the action.
    """
    activity = ActivityLog(
        employee=employee,
        action=action,
        details=details,
        company_id=company_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(activity)
    db.session.commit()



# Utility Function: Check session and redirect if not logged in
def is_logged_in():
    return "employee" in session
    
    
def calculate_days_overdue(date_in):
    from datetime import datetime
    if not date_in:
        return 0
    try:
        # Adjust format based on your A/R file
        date_in_parsed = datetime.strptime(date_in, "%m/%d/%Y")  # Example format: 12/15/2023
        overdue_days = (datetime.now() - date_in_parsed).days
        return max(overdue_days, 0)
    except ValueError:
        return 0  # Handle parsing errors gracefully


        
        
def get_company_details(company_name):
    """
    Retrieve detailed information about a company.
    This is a placeholder for now. Extend this function to fetch from a database or file.
    """
    # Placeholder details for now
    return {
        "address": "123 Main St, Springfield",
        "contact_person": "John Doe",
        "phone": "555-1234",
        "email": "contact@example.com",
        "notes": "Preferred customer. Handles large contracts."
    }
        
# Define Models
class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    contact_person = db.Column(db.String(120))
    phone_number = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.String(250))
    notes = db.Column(db.Text)
    alternative_contacts = db.relationship('AlternativeContact', backref='company', lazy=True)
    contracts = db.relationship('Contract', backref='company', lazy=True)
    activities = db.relationship('ActivityLog', backref='company', lazy=True)

class AlternativeContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)

class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contract_number = db.Column(db.String(50), nullable=False)
    amount_due = db.Column(db.Float, default=0.0)
    date_in = db.Column(db.Date, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    reverted = db.Column(db.Boolean, default=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    employee = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(120))
    details = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)


# Auto-migrate database on app start (for Render or production environments)
@app.before_first_request
def initialize_database():
    with app.app_context():
        upgrade()  # Runs migrations
        
        
@app.context_processor
def inject_now():
    return {"now": datetime.now()}


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        employee = request.form.get("employee")
        if employee:
            session["employee"] = employee  # Store the logged-in employee in the session
            return redirect(url_for("dashboard"))
        else:
            flash("Please select an employee to log in.")
    return render_template("login.html", page_title="Login")



@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Calculate overdue contracts (90+ days overdue)
    overdue_threshold = datetime.now() - timedelta(days=90)
    overdue_contracts = Contract.query.filter(
        Contract.date_in <= overdue_threshold, Contract.paid == False
    ).all()

    # Calculate inactive customers (no activity in 30+ days)
    contact_threshold = datetime.now() - timedelta(days=30)
    inactive_customers = Company.query.filter(
        ~Company.activities.any(ActivityLog.timestamp >= contact_threshold)
    ).all()

    # Pass `now` to the template for date calculations
    now = datetime.now()

    # Render the dashboard with all the required data
    return render_template(
        "dashboard.html",
        employee=session["employee"],
        page_title="Dashboard",
        overdue_contracts=overdue_contracts,
        inactive_customers=inactive_customers,
        now=now,  # Pass current datetime to the template
    )

@app.route("/upload_ar", methods=["GET", "POST"])
def upload_ar():
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename.endswith(".xlsx"):
            try:
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                file.save(filepath)

                # Process the uploaded file
                new_data = process_excel(filepath)

                # Update the database with new data
                for company_name, details in new_data.items():
                    # Check if the company already exists in the database
                    company = Company.query.filter_by(name=company_name).first()
                    if not company:
                        # Add new company if it doesn't exist
                        company = Company(name=company_name)
                        db.session.add(company)
                        db.session.commit()

                    # Process contracts for the company
                    existing_contracts = {c.contract_number: c for c in company.contracts}
                    for contract_data in details["contracts"]:
                        contract_number = contract_data["contract_number"]

                        try:
                            # Check for existing contract and update or create
                            if contract_number in existing_contracts:
                                contract = existing_contracts[contract_number]
                                contract.amount_due = float(contract_data["amount_due"])
                                contract.paid = bool(contract_data["paid"])
                                contract.date_in = datetime.strptime(
                                    contract_data["date_in"], "%m/%d/%Y"
                                )
                            else:
                                # Add new contract
                                new_contract = Contract(
                                    contract_number=contract_number,
                                    amount_due=float(contract_data["amount_due"]),
                                    date_in=datetime.strptime(
                                        contract_data["date_in"], "%m/%d/%Y"
                                    ),
                                    paid=bool(contract_data["paid"]),
                                    company_id=company.id,
                                )
                                db.session.add(new_contract)
                        except Exception as contract_error:
                            print(
                                f"Error processing contract {contract_number} for company {company_name}: {contract_error}"
                            )

                    db.session.commit()

                flash("A/R Report uploaded and processed successfully!", "success")
            except ValueError as ve:
                print(f"ValueError during upload: {ve}")  # Debugging
                flash(str(ve), "error")
            except Exception as e:
                print(f"Unexpected error: {e}")  # Debugging
                flash("An error occurred while processing the file. Please try again.", "error")
        else:
            flash("Invalid file type. Please upload an Excel file.", "error")

    # Retrieve all companies to display on the page
    companies = Company.query.all()
    return render_template(
        "upload_ar.html",
        employee=session["employee"],
        profiles=companies,
        page_title="Upload A/R Report",
    )



@app.route("/current_ar")
def current_ar():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Query all companies and their contracts
    companies = Company.query.all()

    # Calculate total outstanding balance
    total_balance = sum(
        contract.amount_due
        for company in companies
        for contract in company.contracts
        if not contract.paid
    )

    # Structure data for rendering
    ar_report = [
        {
            "company_name": company.name,
            "contracts": [
                {
                    "contract_number": contract.contract_number,
                    "amount_due": contract.amount_due,
                    "date_in": contract.date_in.strftime("%m/%d/%Y"),
                    "paid": contract.paid,
                }
                for contract in company.contracts
            ],
        }
        for company in companies
    ]

    return render_template(
        "current_ar.html",
        employee=session["employee"],
        ar_report=ar_report,
        total_balance=total_balance,  # Pass total balance to the template
        page_title="Current A/R Report",
    )




@app.route("/all_companies")
def all_companies():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Query all companies
    companies = Company.query.all()

    # Prepare data for the template
    companies_data = [
        {
            "id": company.id,
            "name": company.name,
            "contracts_count": len(company.contracts),
            "outstanding_balance": sum(
                contract.amount_due for contract in company.contracts if not contract.paid
            )
        }
        for company in companies
    ]

    # Search/filter functionality
    query = request.args.get("query", "").lower()
    if query:
        companies_data = [
            company for company in companies_data
            if query in company["name"].lower() or query in str(company["outstanding_balance"])
        ]

    return render_template(
        "all_companies.html",
        employee=session["employee"],
        companies=companies_data,
        page_title="All Companies"
    )



@app.route("/company_profile/<int:company_id>")
def company_profile(company_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    # Fetch the company by ID
    company = Company.query.get_or_404(company_id)

    # Retrieve unpaid and paid contracts
    unpaid_contracts = Contract.query.filter_by(company_id=company.id, paid=False).all()
    paid_contracts = Contract.query.filter_by(company_id=company.id, paid=True).all()

    # Retrieve activity logs
    recent_activity = ActivityLog.query.filter_by(company_id=company.id).order_by(ActivityLog.timestamp.desc()).all()

    # Prepare totals
    total_unpaid = sum(contract.amount_due for contract in unpaid_contracts)
    total_paid = sum(contract.amount_due for contract in paid_contracts)

    # Handle missing fields with fallback values
    company.contact_person = company.contact_person or "N/A"
    company.phone_number = company.phone_number or "N/A"
    company.email = company.email or "N/A"
    company.address = company.address or "N/A"
    company.notes = company.notes or "No notes available."

    return render_template(
        "company_profile.html",
        employee=session["employee"],
        page_title=f"{company.name} Profile",
        company=company,  # Changed this to company
        unpaid_contracts=unpaid_contracts,
        paid_contracts=paid_contracts,
        recent_activity=recent_activity,
        total_unpaid=total_unpaid,
        total_paid=total_paid,
    )








@app.route("/update_company_details", methods=["POST"])
def update_company_details():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form.get("company_id")
    company = Company.query.get_or_404(company_id)

    updated_fields = []

    # Check and update each field, log changes if modified
    if request.form["contact_person"] != company.contact_person:
        company.contact_person = request.form["contact_person"]
        updated_fields.append("contact person")

    if request.form["phone_number"] != company.phone_number:
        company.phone_number = request.form["phone_number"]
        updated_fields.append("phone number")

    if request.form["email"] != company.email:
        company.email = request.form["email"]
        updated_fields.append("email")

    if request.form["address"] != company.address:
        company.address = request.form["address"]
        updated_fields.append("address")

    # Handle alternative contacts
    alt_contact_name = request.form.get("alt_contact_name")
    alt_contact_phone = request.form.get("alt_contact_phone")
    alt_contact_email = request.form.get("alt_contact_email")

    if alt_contact_name or alt_contact_phone or alt_contact_email:
        alternative_contact = AlternativeContact(
            name=alt_contact_name,
            phone=alt_contact_phone,
            email=alt_contact_email,
            company_id=company.id
        )
        db.session.add(alternative_contact)
        updated_fields.append("alternative contact")

    # Save changes to the database
    if updated_fields:
        db.session.commit()
        details = f"Employee updated {', '.join(updated_fields)} for {company.name}"
        app.logger.info(details)

        # Log the activity
        activity = ActivityLog(
            company_id=company.id,
            employee=session["employee"],
            action="Update",
            details=details,
            timestamp=datetime.now()
        )
        db.session.add(activity)
        db.session.commit()

    flash(f"Details updated for {company.name}.", "success")
    return redirect(url_for("company_profile", company_id=company.id))





@app.route("/stats")
def stats():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Fetch data
    total_balance = db.session.query(db.func.sum(Contract.amount_due)).filter_by(paid=False).scalar() or 0
    total_contracts = Contract.query.count()
    total_paid_contracts = Contract.query.filter_by(paid=True).count()

    # Fetch actions
    calls_made = ActivityLog.query.filter_by(action="Call Made").count()
    emails_sent = ActivityLog.query.filter_by(action="Email Sent").count()
    attempts_made = calls_made + emails_sent
    payments_made = ActivityLog.query.filter_by(action="Marked as Paid").count()

    return render_template(
        "stats.html",
        employee=session["employee"],
        page_title="Statistics",
        total_balance=total_balance,
        total_contracts=total_contracts,
        total_paid_contracts=total_paid_contracts,
        calls_made=calls_made,
        emails_sent=emails_sent,
        attempts_made=attempts_made,
        payments_made=payments_made,
    )




@app.route("/activity")
def activity():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Fetch all activity logs and distinct employees
    activity_log = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    employees = db.session.query(ActivityLog.employee).distinct().all()

    return render_template(
        "activity.html",
        employee=session["employee"],
        activity_log=activity_log,
        employees=[e[0] for e in employees],  # Extract employee names
        page_title="Activity Log",
    )


@app.route("/toggle_paid_status", methods=["POST"])
def toggle_paid_status():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form.get("company_id")
    contract_number = request.form.get("contract_number")

    if not company_id or not contract_number:
        flash("Missing required information to toggle paid status.", "error")
        return redirect(url_for("all_companies"))

    # Fetch the contract
    contract = Contract.query.filter_by(contract_number=contract_number, company_id=company_id).first()

    if not contract:
        flash("Contract not found.", "error")
        return redirect(url_for("company_profile", company_id=company_id))

    # Toggle the paid status
    if contract.paid:
        contract.paid = False
        action = "Reverted to Unpaid"
    else:
        contract.paid = True
        action = "Marked as Paid"

    db.session.commit()

    # Log the activity
    details = f"Contract {contract_number} {action.lower()}."
    log_activity(session["employee"], action, details, company_id=company_id)

    flash(f"{action} for contract {contract_number}.", "success")
    return redirect(url_for("company_profile", company_id=company_id))  # Redirect back to the company profile




def process_excel(filepath):
    df = pd.read_excel(filepath)
    required_columns = ["Company Name", "Contract #", "A/R Amt", "Date In", "Paid"]

    # Validate required columns
    for column in required_columns:
        if column not in df.columns:
            raise ValueError(f"Missing required column: {column}")

    # Fill missing cells with empty strings to avoid issues
    df.fillna("", inplace=True)

    for _, row in df.iterrows():
        company_name = row["Company Name"]
        if company_name:
            # Check if the company already exists in the database
            company = Company.query.filter_by(name=company_name).first()
            if not company:
                # Add new company with default values for missing fields
                company = Company(
                    name=company_name,
                    contact_person="Unknown Contact",
                    phone_number="N/A",
                    email="N/A",
                    address="N/A",
                    notes="No additional notes provided."
                )
                db.session.add(company)
                db.session.commit()

            # Add or update contracts
            contract = Contract.query.filter_by(contract_number=row["Contract #"], company_id=company.id).first()
            if not contract:
                contract = Contract(
                    company_id=company.id,
                    contract_number=row["Contract #"],
                    amount_due=float(row["A/R Amt"]) if row["A/R Amt"] else 0.0,
                    date_in=datetime.strptime(row["Date In"], "%m/%d/%Y") if row["Date In"] else datetime.now(),
                    paid=row["Paid"] == "Yes"
                )
                db.session.add(contract)
            else:
                # Update contract details if it already exists
                contract.amount_due = float(row["A/R Amt"]) if row["A/R Amt"] else 0.0
                contract.paid = row["Paid"] == "Yes"
                contract.date_in = datetime.strptime(row["Date In"], "%m/%d/%Y") if row["Date In"] else datetime.now()

    db.session.commit()









@app.route("/log_activity", methods=["POST"])
def log_activity_route():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form.get("company_id")
    action = request.form.get("action")
    details = request.form.get("details", "")  # Optional additional details
    employee = session.get("employee", "Unknown Employee")

    if not company_id or not action:
        flash("Invalid activity submission.", "error")
        return redirect(url_for("dashboard"))

    # Log the activity in the database
    log_activity(employee, action, details, company_id=company_id)

    flash(f"Activity logged: {action} for company ID {company_id}.", "success")
    return redirect(url_for("company_profile", company_id=company_id))  # Redirect back to the company profile




@app.route("/update_notes", methods=["POST"])
def update_notes():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form["company_id"]
    notes = request.form["notes"]

    # Update notes in the database
    company = Company.query.get_or_404(company_id)
    company.notes = notes
    db.session.commit()

    flash(f"Notes updated for {company.name}.", "success")
    return redirect(url_for("company_profile", company_id=company_id))  # Redirect back to the company profile



@app.route("/mark_contract_paid", methods=["POST"])
def mark_contract_paid():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_name = request.form["company"]
    contract_number = request.form["contract_number"]

    # Logic to mark the contract as paid...

    employee = session["employee"]
    details = f"{employee} marked contract {contract_number} as paid for {company_name}"
    app.logger.info(details)
    ar_data[company_name].setdefault("activity", []).append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": "Contract Payment",
        "details": details
    })

    flash(f"Contract {contract_number} marked as paid for {company_name}.", "success")
    return redirect(url_for("company_profile", company_name=company_name))
    
    
@app.route("/log_profile_activity", methods=["POST"])
def log_profile_activity():
    """
    Logs activity specific to a company profile and saves it to the ActivityLog table.
    """
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form.get("company_id")  # Use company_id instead of company_name
    action = request.form.get("action")
    details = request.form.get("details", "")  # Optional additional details
    employee = session.get("employee", "Unknown Employee")

    if not company_id or not action:
        flash("Invalid activity submission.", "error")
        return redirect(url_for("dashboard"))

    # Check if the company exists in the database
    company = Company.query.get(company_id)
    if not company:
        flash(f"Company with ID {company_id} not found.", "error")
        return redirect(url_for("dashboard"))

    # Log the activity in the database
    activity = ActivityLog(
        company_id=company.id,
        employee=employee,
        action=action,
        details=details,
        timestamp=datetime.utcnow()
    )
    db.session.add(activity)
    db.session.commit()

    flash(f"Activity logged: {action} for {company.name}.", "success")
    return redirect(url_for("company_profile", company_id=company.id))





if __name__ == "__main__":
    app.run(debug=True)
