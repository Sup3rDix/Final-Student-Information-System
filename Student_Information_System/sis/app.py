"""Menu-driven terminal controller for students, subjects, enrollments, grades and reports."""

from pathlib import Path

from .database import StorageError
from .service import StudentSystem, ValidationError
from .terminal import PALETTES, Terminal


class App:
    def __init__(self, data_dir):
        self.system = StudentSystem(Path(data_dir))
        self.startup_error = None
        try:
            saved_theme = self.system.theme()
        except StorageError as exc:
            saved_theme = "Matrix Green"
            self.startup_error = exc
        self.ui = Terminal(saved_theme)
        self.current_user = None

    @property
    def is_admin(self):
        return bool(self.current_user and self.current_user["role"] == "Administrator")

    def require_admin(self):
        """Protect administrator-only student changes even if called outside a menu."""
        if not self.is_admin:
            raise ValidationError("Administrator access required to change student records.")

    def run(self):
        try:
            if self.startup_error:
                raise self.startup_error
            if not self.system.read("users"):
                self.first_run_setup()
            while True:
                user = self.login()
                if user is None:
                    self.ui.screen("System shutdown")
                    self.ui.success("Data saved. Goodbye!")
                    return
                self.current_user = user
                should_exit = self.dashboard()
                self.current_user = None
                if should_exit:
                    self.ui.screen("System shutdown")
                    self.ui.success("Data saved. Goodbye!")
                    return
        except (KeyboardInterrupt, EOFError):
            print("\nSession ended. Stored records are preserved.")
        except StorageError as exc:
            self.ui.error(str(exc))
            self.ui.error("Resolve the file error and restart. No records have been overwritten.")

    def first_run_setup(self):
        while True:
            self.ui.screen("First-time administrator setup")
            self.ui.info("No user accounts were found. Create the first Administrator account.")
            self.ui.info("Passwords are stored only as salted PBKDF2-SHA256 hashes.")
            self.ui.login_panel(setup=True)
            username = self.ui.ask("Administrator username (3-24 characters)")
            password = self.ui.ask_secret("New password (8+ characters, letters and numbers)")
            confirm = self.ui.ask_secret("Confirm new password")
            if password != confirm:
                self.ui.error("Passwords do not match.")
                self.ui.pause()
                continue
            try:
                user = self.system.create_initial_admin(username, password)
            except ValidationError as exc:
                self.ui.error(str(exc))
                self.ui.pause()
                continue
            self.ui.success(f"Administrator '{user['username']}' created successfully.")
            self.ui.pause()
            return

    def login(self):
        attempts = 0
        while attempts < 3:
            self.ui.screen("Secure user login")
            self.ui.info("Administrator and Staff accounts are supported.")
            self.ui.info("Enter 0 as the username to shut down.")
            self.ui.login_panel()
            username = self.ui.ask("Username")
            if username == "0":
                return None
            password = self.ui.ask_secret("Password")
            user = self.system.authenticate(username, password)
            if user:
                return user
            attempts += 1
            self.ui.error(f"Invalid credentials or inactive account. Attempts left: {3 - attempts}")
            if attempts < 3:
                self.ui.pause()
        self.ui.error("Maximum login attempts reached for this session.")
        return None

    def action(self, fn):
        try:
            fn()
        except (ValidationError, StorageError, OSError, ValueError) as exc:
            self.ui.error(str(exc))
        self.ui.pause()

    def dashboard_metrics(self):
        """Calculate live dashboard counters without modifying any data files."""
        students = self.system.read("students")
        grades = self.system.read("grades")
        return {
            "students": len(students),
            "active": sum(s["status"] == "Active" for s in students),
            "subjects": len(self.system.read("subjects")),
            "enrollments": len(self.system.read("enrollments")),
            "graded": len(grades),
            "passing": sum(g["remarks"] == "Passed" for g in grades),
            "failing": sum(g["remarks"] == "Failed" for g in grades),
        }

    def dashboard(self):
        while True:
            self.ui.screen("Main dashboard")
            self.ui.dashboard_cards(self.current_user, self.dashboard_metrics())
            if not self.system.read("students"):
                if self.is_admin:
                    self.ui.info("No students yet. Choose Students > Add student to register the first learner.")
                else:
                    self.ui.info("No students yet. An Administrator must register student profiles.")
            options = [("1", "Students / profiles & search"),
                       ("2", "Subjects / course catalog"),
                       ("3", "Enrollments / registration"),
                       ("4", "Grades / grade center"),
                       ("5", "Reports / analytics & export"),
                       ("6", "Settings / theme & security")]
            if self.is_admin:
                options.append(("7", "User accounts / admin tools"))
            options.append(("9", "Exit system"))
            choice = self.ui.menu("DASHBOARD NAVIGATION", options, "Logout (return to login)")
            if choice == "0":
                return False
            if choice == "9" and self.ui.yes_no("Exit the system now?"):
                return True
            actions = {"1": self.students_menu, "2": self.subjects_menu,
                       "3": self.enrollments_menu, "4": self.grades_menu,
                       "5": self.reports_menu, "6": self.settings_menu,
                       "7": self.users_menu}
            if choice in actions and (choice != "7" or self.is_admin):
                actions[choice]()

    def students_table(self, rows):
        self.ui.table(["STUDENT ID", "FULL NAME", "PROGRAM", "YEAR", "STATUS"],
                      [[s["student_id"], s["full_name"], s["program"], s["year_level"], s["status"]]
                       for s in rows], [12, 26, 14, 5, 10])

    def students_menu(self):
        while True:
            self.ui.screen("Student records")
            choices = [("1", "List all students")]
            if self.is_admin:
                choices.append(("2", "Add student"))
            choices.append(("3", "Search students"))
            if self.is_admin:
                choices.extend([("4", "Edit student"),
                                ("5", "Delete student (only if not enrolled)")])
            choice = self.ui.menu("STUDENT MANAGEMENT", choices)
            if choice == "0":
                return
            actions = {"1": self.show_students, "2": self.add_student,
                       "3": self.search_students, "4": self.edit_student, "5": self.delete_student}
            self.action(actions[choice])

    def show_students(self):
        self.students_table(self.system.read("students"))

    def add_student(self):
        self.require_admin()
        s = self.system.add_student(self.ui.ask("Full name"), self.ui.ask("Program (e.g. BSIT)"),
                                    self.ui.ask("Year level (1-6)"), self.ui.ask("Email"))
        self.ui.success(f"Saved student {s['student_id']} - {s['full_name']}")

    def search_students(self):
        term = self.ui.ask("Search ID / name / program / email / status")
        self.students_table(self.system.search_students(term))

    def edit_student(self):
        self.require_admin()
        ident = self.ui.ask("Student ID to edit").upper()
        students = self.system.read("students")
        row = next((s for s in students if s["student_id"] == ident), None)
        if row is None:
            raise ValidationError("Student not found.")
        self.ui.info("Press ENTER to retain the value shown in [brackets].")
        updates = {"full_name": self.ui.ask("Full name", row["full_name"]),
                   "program": self.ui.ask("Program", row["program"]),
                   "year_level": self.ui.ask("Year level", row["year_level"]),
                   "email": self.ui.ask("Email", row["email"]),
                   "status": self.ui.ask("Status: Active / Inactive / Graduated", row["status"]).title()}
        self.system.update_student(ident, **updates)
        self.ui.success("Student profile updated in students.txt.")

    def delete_student(self):
        self.require_admin()
        ident = self.ui.ask("Student ID to delete").upper()
        if self.ui.yes_no(f"Permanently delete {ident}?"):
            self.system.delete_student(ident)
            self.ui.success("Student deleted.")

    def subjects_table(self, rows):
        self.ui.table(["CODE", "SUBJECT TITLE", "UNITS", "INSTRUCTOR"],
                      [[s["code"], s["title"], s["units"], s["instructor"]] for s in rows],
                      [12, 34, 5, 25])

    def subjects_menu(self):
        while True:
            self.ui.screen("Subject catalog")
            choices = [("1", "List all subjects"), ("2", "Search subjects")]
            if self.is_admin:
                choices.extend([("3", "Add subject"), ("4", "Edit subject"),
                                ("5", "Delete subject (if unused)")])
            choice = self.ui.menu("SUBJECT MANAGEMENT", choices)
            if choice == "0":
                return
            self.action({"1": self.show_subjects, "2": self.search_subjects,
                         "3": self.add_subject, "4": self.edit_subject,
                         "5": self.delete_subject}[choice])

    def show_subjects(self):
        self.subjects_table(self.system.read("subjects"))

    def search_subjects(self):
        self.subjects_table(self.system.search_subjects(self.ui.ask("Search code / title / instructor")))

    def add_subject(self):
        row = self.system.add_subject(self.ui.ask("Subject code"), self.ui.ask("Subject title"),
                                      self.ui.ask("Units (1-6)"), self.ui.ask("Instructor"))
        self.ui.success(f"Created subject {row['code']}.")

    def edit_subject(self):
        code = self.ui.ask("Subject code to edit").upper()
        subjects = self.system.read("subjects")
        row = next((s for s in subjects if s["code"] == code), None)
        if not row:
            raise ValidationError("Subject not found.")
        updates = {"title": self.ui.ask("Title", row["title"]),
                   "units": self.ui.ask("Units", row["units"]),
                   "instructor": self.ui.ask("Instructor", row["instructor"])}
        self.system.update_subject(code, **updates)
        self.ui.success("Subject updated.")

    def delete_subject(self):
        code = self.ui.ask("Subject code to delete").upper()
        if self.ui.yes_no(f"Permanently delete subject {code}?"):
            self.system.delete_subject(code)
            self.ui.success("Subject deleted.")

    def enrollments_table(self, entries):
        self.ui.table(["ENROLL ID", "STUDENT", "SUBJECT", "SEMESTER", "SCHOOL YEAR"],
                      [[e["enrollment_id"], e["student_name"], e["subject_code"],
                        e["semester"], e["school_year"]] for e in entries],
                      [11, 25, 10, 13, 11])

    def enrollments_menu(self):
        while True:
            self.ui.screen("Enrollment management")
            choice = self.ui.menu("ENROLLMENT OPERATIONS", [("1", "List enrollments"),
                ("2", "Enroll a student"), ("3", "Search enrollments"),
                ("4", "Withdraw enrollment (without recorded grade)")])
            if choice == "0":
                return
            self.action({"1": self.show_enrollments, "2": self.enroll_student,
                         "3": self.search_enrollments, "4": self.withdraw_enrollment}[choice])

    def show_enrollments(self):
        self.enrollments_table(self.system.list_enrollments())

    def enroll_student(self):
        self.ui.info("Use student ID and subject code from their respective menus.")
        sid = self.ui.ask("Student ID").upper()
        code = self.ui.ask("Subject code").upper()
        sem_choice = self.ui.ask("Semester (1=First, 2=Second, 3=Summer)")
        semester = {"1": "1st Semester", "2": "2nd Semester", "3": "Summer"}.get(sem_choice, "")
        school_year = self.ui.ask("School year", "2026-2027")
        e = self.system.enroll(sid, code, semester, school_year)
        self.ui.success(f"Enrolled successfully: {e['enrollment_id']}")

    def search_enrollments(self):
        self.enrollments_table(self.system.list_enrollments(self.ui.ask("Search ID / student / subject / term")))

    def withdraw_enrollment(self):
        ident = self.ui.ask("Enrollment ID").upper()
        if self.ui.yes_no(f"Withdraw {ident}?"):
            self.system.withdraw(ident)
            self.ui.success("Enrollment removed.")

    def grades_table(self, entries):
        self.ui.table(["ENROLL ID", "STUDENT", "SUBJECT", "PRE", "MID", "FINAL", "AVG", "REMARKS"],
                      [[g["enrollment_id"], g["student_name"], g["subject_code"],
                        f"{g['prelim']:.1f}", f"{g['midterm']:.1f}", f"{g['final_exam']:.1f}",
                        f"{g['average']:.1f}", g["remarks"]] for g in entries],
                      [10, 21, 9, 5, 5, 5, 5, 7])

    def grades_menu(self):
        while True:
            self.ui.screen("Grade management")
            choices = [("1", "List all recorded grades"), ("2", "Record or update grade"),
                       ("3", "Search grades")]
            if self.is_admin:
                choices.append(("4", "Delete a recorded grade"))
            choice = self.ui.menu("GRADE OPERATIONS - 30% PRE / 30% MID / 40% FINAL", choices)
            if choice == "0":
                return
            self.action({"1": self.show_grades, "2": self.record_grade,
                         "3": self.search_grades, "4": self.delete_grade}[choice])

    def show_grades(self):
        self.grades_table(self.system.list_grades())

    def record_grade(self):
        ident = self.ui.ask("Enrollment ID").upper()
        grade = self.system.save_grade(ident, self.ui.ask("Prelim (0-100)"),
                                       self.ui.ask("Midterm (0-100)"),
                                       self.ui.ask("Final exam (0-100)"))
        self.ui.success(f"Saved: {grade['average']:.2f} ({grade['remarks']}).")

    def search_grades(self):
        self.grades_table(self.system.list_grades(self.ui.ask("Search student / enrollment / subject / remarks")))

    def delete_grade(self):
        ident = self.ui.ask("Enrollment ID whose grade will be deleted").upper()
        if self.ui.yes_no(f"Permanently remove grade for {ident}?"):
            self.system.delete_grade(ident)
            self.ui.success("Grade deleted.")

    def reports_menu(self):
        while True:
            self.ui.screen("Reports and summaries")
            choice = self.ui.menu("REPORT CENTER", [("1", "Population by program, year and status"),
                ("2", "Performance by subject, with passing rates"),
                ("3", "Individual student report card")])
            if choice == "0":
                return
            self.action(lambda c=choice: self.generate_report(c))

    def generate_report(self, choice):
        if choice == "1":
            name, body = "population", self.system.population_report()
        elif choice == "2":
            name, body = "performance", self.system.performance_report()
        else:
            ident = self.ui.ask("Student ID for report card").upper()
            name, body = f"report_card_{ident}", self.system.student_report_card(ident)
        self.ui.rule()
        self.ui.paragraph(body)
        if self.ui.yes_no("Export this report to the reports folder?", default=True):
            path = self.system.export_report(name, body)
            self.ui.success(f"Report exported: {path}")

    def settings_menu(self):
        while True:
            self.ui.screen("System settings")
            choice = self.ui.menu("PREFERENCES", [("1", "Change terminal color theme"),
                ("2", "Update my password"), ("3", "View storage and security information")])
            if choice == "0":
                return
            self.action({"1": self.change_theme, "2": self.update_my_password,
                         "3": self.storage_info}[choice])

    def change_theme(self):
        choice = self.ui.theme_menu()
        if choice != "0":
            name = list(PALETTES)[int(choice) - 1]
            self.system.set_theme(name)
            self.ui.theme = name
            self.ui.screen("New theme activated")
            self.ui.success(f"Theme set to {name}. It will persist after restart.")
            self.ui.info(PALETTES[name]["description"])

    def update_my_password(self):
        old = self.ui.ask_secret("Current password")
        new = self.ui.ask_secret("New password")
        confirm = self.ui.ask_secret("Confirm new password")
        if new != confirm:
            raise ValidationError("New passwords do not match.")
        self.system.change_password(self.current_user["username"], old, new)
        self.ui.success("Password updated securely.")

    def storage_info(self):
        self.ui.info(f"Text database directory: {self.system.data_dir}")
        for name, store in self.system.stores.items():
            self.ui.text(f"    {store.path.name:<19} {len(store.load()):>5} records")
        self.ui.info("Format: one JSON object per line in each .txt file.")
        self.ui.info("New records append; updates/deletes use atomic file rewrites.")
        self.ui.info("Passwords: salted PBKDF2-HMAC-SHA256, 600,000 iterations.")

    def users_menu(self):
        if not self.is_admin:
            return
        while True:
            self.ui.screen("User account management")
            choice = self.ui.menu("ADMINISTRATOR OPTIONS", [("1", "List users (no password details)"),
                ("2", "Create Administrator or Staff"), ("3", "Enable / disable account"),
                ("4", "Reset a user's password")])
            if choice == "0":
                return
            self.action({"1": self.list_users, "2": self.add_user,
                         "3": self.toggle_user, "4": self.reset_user_password}[choice])

    def list_users(self):
        self.ui.table(["USERNAME", "ROLE", "STATUS", "CREATED"],
                      [[u["username"], u["role"], "Active" if u["active"] else "Disabled",
                        u["created_at"][:10]] for u in self.system.read("users")],
                      [22, 15, 10, 12])

    def add_user(self):
        username = self.ui.ask("New username")
        role_choice = self.ui.ask("Role: 1=Administrator, 2=Staff")
        role = {"1": "Administrator", "2": "Staff"}.get(role_choice, "")
        password = self.ui.ask_secret("New user's password")
        confirm = self.ui.ask_secret("Confirm password")
        if password != confirm:
            raise ValidationError("Passwords do not match.")
        new_user = self.system.create_user(username, password, role)
        self.ui.success(f"Created {new_user['role']} account: {new_user['username']}")

    def toggle_user(self):
        username = self.ui.ask("Username to enable / disable").lower()
        choice = self.ui.ask("1=Enable, 2=Disable")
        if choice not in ("1", "2"):
            raise ValidationError("Choose 1 or 2.")
        self.system.set_user_active(username, choice == "1", self.current_user["username"])
        self.ui.success("Account status updated.")

    def reset_user_password(self):
        username = self.ui.ask("Username to reset").lower()
        new_password = self.ui.ask_secret("Set new password")
        confirm = self.ui.ask_secret("Confirm new password")
        if new_password != confirm:
            raise ValidationError("Passwords do not match.")
        self.system.reset_password(username, new_password)
        self.ui.success(f"Password for '{username}' reset. Share the new password privately.")
