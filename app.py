from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
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


@app.route('/run-migrations', methods=['GET'])
def run_migrations():
    from flask_migrate import upgrade
    try:
        upgrade()  # Runs the migration script to initialize or update the database
        return "Database migrations applied successfully!", 200
    except Exception as e:
        return f"An error occurred: {e}", 500

@app.route("/reset-database", methods=["GET"])
def reset_database():
    """
    Reset the database by dropping all tables and recreating them.
    USE WITH CAUTION! This should only be enabled in a safe testing environment.
    """
    if not is_logged_in():  # Optional: Check if the user is logged in
        return "Unauthorized access. Please log in.", 403

    from flask_migrate import upgrade
    try:
        # Drop all tables
        db.drop_all()
        # Recreate tables
        db.create_all()
        # Optionally run migrations after recreation
        upgrade()
        return "Database has been reset successfully!", 200
    except Exception as e:
        return f"An error occurred during database reset: {e}", 500

        
        
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
    
@app.route("/logout")
def logout():
    session.pop("employee", None)  # Remove 'employee' from the session
    return redirect(url_for("login"))



@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Recent activities
    recent_activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()

    # Overdue contracts (90+ days)
    overdue_contracts = Contract.query.filter(
        Contract.date_in <= datetime.now() - timedelta(days=90),
        Contract.paid == False
    ).all()

    # Inactive customers (no contact in 30+ days)
    inactive_customers = Company.query.outerjoin(ActivityLog).filter(
        (datetime.now() - ActivityLog.timestamp >= timedelta(days=30)) |
        (ActivityLog.timestamp == None)  # Handles companies with no activity
    ).distinct().all()

    # Key metrics
    total_contracts = Contract.query.count()
    total_unpaid_balance = db.session.query(db.func.sum(Contract.amount_due)).filter_by(paid=False).scalar() or 0
    total_paid_balance = db.session.query(db.func.sum(Contract.amount_due)).filter_by(paid=True).scalar() or 0
    total_companies = Company.query.count()

    return render_template(
        "dashboard.html",
        employee=session["employee"],
        recent_activities=recent_activities,
        overdue_contracts=overdue_contracts,
        inactive_customers=inactive_customers,
        total_contracts=total_contracts,
        total_unpaid_balance=total_unpaid_balance,
        total_paid_balance=total_paid_balance,
        total_companies=total_companies
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
                process_excel(filepath)

                flash("A/R Report uploaded and processed successfully!", "success")
            except ValueError as ve:
                app.logger.error(f"ValueError during upload: {ve}")
                flash(str(ve), "error")
            except Exception as e:
                app.logger.error(f"Unexpected error during upload: {e}")
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

    # Query all companies and their contracts, sorted alphabetically by company name
    companies = Company.query.order_by(Company.name).all()

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

    # Query all companies sorted alphabetically
    companies = Company.query.order_by(Company.name.asc()).all()

    # Prepare data for each category
    uncontacted_unpaid = []
    contacted_unpaid = []
    paid_companies = []

    for company in companies:
        unpaid_contracts = [contract for contract in company.contracts if not contract.paid]
        total_unpaid = sum(contract.amount_due for contract in unpaid_contracts)
        overdue_contracts = [
            contract for contract in unpaid_contracts if (datetime.utcnow().date() - contract.date_in).days > 30
        ]
        last_activity = (
            db.session.query(ActivityLog.timestamp)
            .filter_by(company_id=company.id)
            .order_by(ActivityLog.timestamp.desc())
            .first()
        )
        last_contact_date = last_activity[0].strftime("%Y-%m-%d") if last_activity else "No activity logged"

        # Categorize companies
        if unpaid_contracts:
            if last_activity and (datetime.utcnow().date() - datetime.strptime(last_contact_date, "%Y-%m-%d").date()).days <= 7:
                contacted_unpaid.append({
                    "id": company.id,
                    "name": company.name,
                    "unpaid_contracts": len(unpaid_contracts),
                    "total_unpaid": total_unpaid,
                    "overdue_contracts": len(overdue_contracts),
                    "last_contact_date": last_contact_date,
                })
            else:
                uncontacted_unpaid.append({
                    "id": company.id,
                    "name": company.name,
                    "unpaid_contracts": len(unpaid_contracts),
                    "total_unpaid": total_unpaid,
                    "overdue_contracts": len(overdue_contracts),
                    "last_contact_date": last_contact_date,
                })
        else:
            paid_companies.append({
                "id": company.id,
                "name": company.name,
                "last_contact_date": last_contact_date,
            })

    # Search/filter functionality
    query = request.args.get("query", "").lower()
    if query:
        uncontacted_unpaid = [
            company for company in uncontacted_unpaid
            if query in company["name"].lower() or query in str(company["total_unpaid"])
        ]
        contacted_unpaid = [
            company for company in contacted_unpaid
            if query in company["name"].lower() or query in str(company["total_unpaid"])
        ]
        paid_companies = [
            company for company in paid_companies
            if query in company["name"].lower()
        ]

    return render_template(
        "all_companies.html",
        employee=session["employee"],
        uncontacted_unpaid=uncontacted_unpaid,
        contacted_unpaid=contacted_unpaid,
        paid_companies=paid_companies,
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


@app.route("/current_contact", methods=["GET", "POST"])
def current_contact():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Fetch customers who have unpaid contracts and no activity in the past 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    customers = (
        Company.query.join(Contract)
        .filter(
            Contract.paid == False,
            ~Company.activities.any(ActivityLog.timestamp >= seven_days_ago),
        )
        .distinct()
        .all()
    )

    # Structure data for frontend
    current_contacts = [
        {
            "id": customer.id,
            "name": customer.name,
            "contact_person": customer.contact_person or "Unknown Contact",
            "phone": customer.phone_number or "N/A",
            "email": customer.email or "N/A",
            "address": customer.address or "N/A",
            "notes": customer.notes or "No notes available",
            "contracts": [
                {
                    "id": contract.id,
                    "contract_number": contract.contract_number,
                    "amount_due": contract.amount_due,
                    "date_in": contract.date_in.strftime("%m/%d/%Y"),
                }
                for contract in customer.contracts if not contract.paid
            ],
        }
        for customer in customers
    ]

    if request.method == "POST":
        # Handle marking a contact as contacted and/or marking contracts as paid
        customer_id = request.form.get("customer_id")
        contract_id = request.form.get("contract_id", None)
        action = request.form.get("action")
        notes = request.form.get("notes", "")

        customer = Company.query.get_or_404(customer_id)

        if action == "mark_paid" and contract_id:
            contract = Contract.query.get_or_404(contract_id)
            contract.paid = True
            db.session.commit()

        if action == "contacted":
            log_activity(
                session.get("employee", "Unknown Employee"),
                "Contacted",
                f"Contacted {customer.name}. Notes: {notes}",
                company_id=customer_id,
            )

        return jsonify({"status": "success"})

    return render_template(
        "current_contact.html",
        current_contacts=current_contacts,
        employee=session.get("employee"),
        page_title="Current Contact",
    )


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

    # Dictionary to track processed companies and contracts
    processed_contracts = {}

    # Initialize variables to handle the "Self-Pay" section
    in_self_pay_section = False

    for _, row in df.iterrows():
        company_name = row["Company Name"]

        # Detect "Self-Pay" block
        if not company_name and row["Contract #"].startswith("ROME-") and row["A/R Amt"]:
            in_self_pay_section = True
            company_name = "SELF-PAY"

        # If in "Self-Pay" section, use column B as the individual's name
        if in_self_pay_section and not row["Company Name"]:
            company_name = row["Contract #"]  # Use Contract Number as a temporary name
            individual_name = row["Contract #"]

            # Handle "Self-Pay" entries
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
                        notes="No additional notes provided.",
                    )
                    db.session.add(company)
                    db.session.commit()  # Commit to assign an ID to the new company

                # Track contracts for this company
                if company.id not in processed_contracts:
                    processed_contracts[company.id] = set()

                # Add or update contracts
                contract_number = row["Contract #"]
                if contract_number and contract_number not in processed_contracts[company.id]:
                    processed_contracts[company.id].add(contract_number)
                    contract = Contract.query.filter_by(
                        contract_number=contract_number, company_id=company.id
                    ).first()
                    if not contract:
                        # Create a new contract
                        try:
                            contract = Contract(
                                company_id=company.id,
                                contract_number=contract_number,
                                amount_due=float(row["A/R Amt"]) if row["A/R Amt"] else 0.0,
                                date_in=datetime.strptime(row["Date In"], "%m/%d/%Y")
                                if row["Date In"]
                                else datetime.now(),
                                paid=row["Paid"] == "Yes",
                            )
                            db.session.add(contract)
                        except Exception as e:
                            app.logger.error(f"Error adding contract: {e}")
                    else:
                        # Update contract details if it already exists
                        try:
                            contract.amount_due = float(row["A/R Amt"]) if row["A/R Amt"] else 0.0
                            contract.paid = row["Paid"] == "Yes"
                            contract.date_in = datetime.strptime(row["Date In"], "%m/%d/%Y") if row["Date In"] else datetime.now()
                        except Exception as e:
                            app.logger.error(f"Error updating contract: {e}")

    # Handle contracts for companies missing in the uploaded file
    all_company_ids = {company.id for company in Company.query.all()}
    for company_id in all_company_ids:
        # If a company is missing entirely from the upload
        if company_id not in processed_contracts:
            contracts_to_mark_paid = Contract.query.filter_by(company_id=company_id, paid=False).all()
            for contract in contracts_to_mark_paid:
                contract.paid = True  # Mark as paid
                log_activity(
                    employee="System",
                    action="Marked as Paid",
                    details=f"Contract {contract.contract_number} automatically marked as paid during upload.",
                    company_id=company_id,
                )
        else:
            # For companies in the upload, check for missing contracts
            uploaded_contracts = processed_contracts[company_id]
            existing_contracts = Contract.query.filter_by(company_id=company_id).all()
            for contract in existing_contracts:
                if contract.contract_number not in uploaded_contracts and not contract.paid:
                    contract.paid = True  # Mark as paid
                    log_activity(
                        employee="System",
                        action="Marked as Paid",
                        details=f"Contract {contract.contract_number} automatically marked as paid during upload.",
                        company_id=company_id,
                    )

    # Commit all changes at once
    try:
        db.session.commit()
        app.logger.info("All contracts processed and committed successfully.")
    except Exception as e:
        app.logger.error(f"Error during commit: {e}")





@app.route("/log_activity", methods=["POST"])
def log_activity_route():
    if not is_logged_in():
        return redirect(url_for("login"))

    # Extract form data
    company_id = request.form.get("company_id")
    action = request.form.get("action")
    details = request.form.get("details", "").strip()  # Optional additional details
    employee = session.get("employee", "Unknown Employee")

    # Validation for required fields
    if not company_id or not action:
        flash("Invalid activity submission.", "error")
        return redirect(url_for("dashboard"))

    # Fetch the company for meaningful details
    company = Company.query.get(company_id)
    company_name = company.name if company else "Unknown Company"

    # Generate fallback details if none are provided
    if not details:
        if action == "Email Sent":
            details = f"An email was sent regarding the profile of {company_name}."
        elif action == "Call Made":
            details = f"A call was made regarding the profile of {company_name}."
        elif action == "Call Received":
            details = f"A call was received regarding the profile of {company_name}."
        elif action == "Marked as Paid":
            details = f"The contract for {company_name} was marked as paid."
        elif action == "Added Note":
            details = f"A new note was added to the profile of {company_name}."
        else:
            details = f"{action} performed for the profile of {company_name}."

    # Log the activity in the database
    log_activity(employee, action, details, company_id=company_id)

    # Notify the user and redirect to the company profile
    flash(f"Activity logged: {action} for company {company_name}.", "success")
    return redirect(url_for("company_profile", company_id=company_id))







@app.route("/update_notes", methods=["POST"])
def update_notes():
    if not is_logged_in():
        return redirect(url_for("login"))

    company_id = request.form["company_id"]
    new_note = request.form["notes"].strip()

    # Fetch the company and append the new note
    company = Company.query.get_or_404(company_id)
    if company.notes:
        company.notes += f"\n{new_note}"  # Append new note with a newline
    else:
        company.notes = new_note  # Add first note if none exist

    db.session.commit()

    # Log the note addition in the activity log
    log_activity(
        session.get("employee", "Unknown"),
        "Added Note",
        f"New note added: {new_note}",
        company_id=company.id
    )

    flash(f"Note added to {company.name}.", "success")
    return redirect(url_for("company_profile", company_id=company.id))



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
