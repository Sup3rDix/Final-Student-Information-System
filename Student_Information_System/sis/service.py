"""All record operations, relationships, validation, reports, and authentication."""

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .database import TextStore, StorageError
from .security import password_fields, password_is_valid, verify_password


class ValidationError(Exception):
    """A user-entered value or operation is not allowed."""


def current_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def required(value, label, limit=80):
    value = str(value).strip()
    if not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > limit:
        raise ValidationError(f"{label} must be at most {limit} characters.")
    return value


def next_id(rows, field, prefix, digits=4):
    values = [int(row[field][len(prefix):]) for row in rows
              if isinstance(row.get(field), str) and row[field].startswith(prefix)
              and row[field][len(prefix):].isdigit()]
    return f"{prefix}{max(values, default=0) + 1:0{digits}d}"


def find_one(rows, field, value, label):
    for row in rows:
        if str(row.get(field, "")).upper() == str(value).strip().upper():
            return row
    raise ValidationError(f"{label} '{value}' not found.")


# Minimal record schemas protect the rest of the app against manually damaged files.
SCHEMAS = {
    "users": {"username": str, "role": str, "active": bool, "salt": str,
              "password_hash": str, "iterations": int, "created_at": str},
    "students": {"student_id": str, "full_name": str, "program": str,
                 "year_level": int, "email": str, "status": str, "created_at": str},
    "subjects": {"code": str, "title": str, "units": int, "instructor": str},
    "enrollments": {"enrollment_id": str, "student_id": str, "subject_code": str,
                    "semester": str, "school_year": str, "enrolled_at": str},
    "grades": {"enrollment_id": str, "prelim": (int, float),
               "midterm": (int, float), "final_exam": (int, float),
               "average": (int, float), "remarks": str, "updated_at": str},
    "settings": {"theme": str},
}


class StudentSystem:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.stores = {
            name: TextStore(self.data_dir, name)
            for name in ("users", "students", "subjects", "enrollments", "grades", "settings")
        }
        self.report_dir = self.data_dir.parent / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def read(self, name):
        rows = self.stores[name].load()
        for line, row in enumerate(rows, 1):
            for field, kind in SCHEMAS[name].items():
                if field not in row or not isinstance(row[field], kind):
                    raise StorageError(
                        f"Malformed record in {name}.txt (entry {line}): "
                        f"'{field}' is missing or has an invalid type."
                    )
        return rows

    @staticmethod
    def available_themes():
        from .terminal import PALETTES
        return tuple(PALETTES)

    def theme(self):
        settings = self.read("settings")
        name = settings[0].get("theme") if settings else None
        return name if name in self.available_themes() else "Matrix Green"

    def set_theme(self, name):
        if name not in self.available_themes():
            raise ValidationError("Unknown color theme.")
        self.stores["settings"].save([{"theme": name}])

    # Authentication and role management
    def create_initial_admin(self, username, password):
        if self.read("users"):
            raise ValidationError("Initial administrator already exists.")
        return self.create_user(username, password, "Administrator")

    def create_user(self, username, password, role):
        username = required(username, "Username", 24).lower()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,23}", username):
            raise ValidationError("Username: 3-24 characters, starts with a letter; use a-z, 0-9, . _ -")
        if role not in ("Administrator", "Staff"):
            raise ValidationError("Role must be Administrator or Staff.")
        if not password_is_valid(password):
            raise ValidationError("Password must have 8+ characters, including letters and numbers.")
        users = self.read("users")
        if any(row.get("username") == username for row in users):
            raise ValidationError("That username already exists.")
        user = {"username": username, "role": role, "active": True,
                "created_at": current_timestamp(), **password_fields(password)}
        self.stores["users"].append(user)
        return {"username": username, "role": role}

    def authenticate(self, username, password):
        for user in self.read("users"):
            if user.get("username") == username.strip().lower() and user.get("active") is True:
                if verify_password(password, user):
                    return {"username": user["username"], "role": user["role"]}
        return None

    def change_password(self, username, current_password, new_password):
        users = self.read("users")
        user = find_one(users, "username", username, "User")
        if not verify_password(current_password, user):
            raise ValidationError("Your current password is incorrect.")
        if not password_is_valid(new_password):
            raise ValidationError("New password must have 8+ characters with letters and numbers.")
        if verify_password(new_password, user):
            raise ValidationError("Choose a password different from the current password.")
        user.update(password_fields(new_password))
        self.stores["users"].save(users)

    def reset_password(self, username, new_password):
        if not password_is_valid(new_password):
            raise ValidationError("Password must have 8+ characters with letters and numbers.")
        users = self.read("users")
        user = find_one(users, "username", username, "User")
        user.update(password_fields(new_password))
        self.stores["users"].save(users)

    def set_user_active(self, username, active, actor):
        if username == actor:
            raise ValidationError("You cannot deactivate your own account.")
        users = self.read("users")
        user = find_one(users, "username", username, "User")
        if not active and user["role"] == "Administrator":
            remaining = [row for row in users if row["role"] == "Administrator"
                         and row["active"] and row["username"] != username]
            if not remaining:
                raise ValidationError("Cannot deactivate the last active administrator.")
        user["active"] = bool(active)
        self.stores["users"].save(users)

    # Students
    def add_student(self, full_name, program, year_level, email):
        full_name = required(full_name, "Student name", 70)
        program = required(program, "Program", 30).upper()
        try:
            year_level = int(year_level)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Year level must be a whole number (1-6).") from exc
        if year_level not in range(1, 7):
            raise ValidationError("Year level must be from 1 to 6.")
        email = required(email, "Email", 100).lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationError("Enter a valid email address.")
        students = self.read("students")
        if any(row.get("email", "").lower() == email for row in students):
            raise ValidationError("A student with this email already exists.")
        student = {"student_id": next_id(students, "student_id", "STU"),
                   "full_name": full_name, "program": program, "year_level": year_level,
                   "email": email, "status": "Active", "created_at": current_timestamp()}
        self.stores["students"].append(student)
        return student

    def update_student(self, student_id, **changes):
        students = self.read("students")
        row = find_one(students, "student_id", student_id, "Student")
        allowed = {"full_name", "program", "year_level", "email", "status"}
        if not set(changes).issubset(allowed):
            raise ValidationError("Invalid student field.")
        candidate = {**row, **changes}
        name = required(candidate["full_name"], "Student name", 70)
        program = required(candidate["program"], "Program", 30).upper()
        try:
            year = int(candidate["year_level"])
        except (ValueError, TypeError) as exc:
            raise ValidationError("Year level must be an integer (1-6).") from exc
        if year not in range(1, 7):
            raise ValidationError("Year level must be from 1 to 6.")
        email = required(candidate["email"], "Email", 100).lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationError("Enter a valid email address.")
        if any(s["student_id"] != row["student_id"] and s["email"].lower() == email
               for s in students):
            raise ValidationError("Email already belongs to another student.")
        if candidate["status"] not in ("Active", "Inactive", "Graduated"):
            raise ValidationError("Status must be Active, Inactive, or Graduated.")
        row.update(full_name=name, program=program, year_level=year,
                   email=email, status=candidate["status"])
        self.stores["students"].save(students)
        return row

    def delete_student(self, student_id):
        students = self.read("students")
        row = find_one(students, "student_id", student_id, "Student")
        if any(e["student_id"] == row["student_id"] for e in self.read("enrollments")):
            raise ValidationError("Cannot delete a student with enrollments. Mark Inactive instead.")
        self.stores["students"].save([s for s in students if s is not row])

    def search_students(self, term):
        term = term.strip().lower()
        return [s for s in self.read("students") if any(
            term in str(s.get(field, "")).lower()
            for field in ("student_id", "full_name", "program", "email", "status"))]

    # Subjects
    def add_subject(self, code, title, units, instructor):
        code = required(code, "Subject code", 15).upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,14}", code):
            raise ValidationError("Subject code: 2-15 letters, digits or hyphens.")
        title = required(title, "Subject title", 70)
        instructor = required(instructor, "Instructor", 70)
        try:
            units = int(units)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Units must be a whole number from 1 to 6.") from exc
        if units not in range(1, 7):
            raise ValidationError("Units must be from 1 to 6.")
        if any(row["code"].upper() == code for row in self.read("subjects")):
            raise ValidationError("This subject code already exists.")
        subject = {"code": code, "title": title, "units": units, "instructor": instructor}
        self.stores["subjects"].append(subject)
        return subject

    def update_subject(self, code, **changes):
        subjects = self.read("subjects")
        row = find_one(subjects, "code", code, "Subject")
        if not set(changes).issubset({"title", "units", "instructor"}):
            raise ValidationError("Invalid subject field.")
        candidate = {**row, **changes}
        title = required(candidate["title"], "Subject title", 70)
        instructor = required(candidate["instructor"], "Instructor", 70)
        try:
            units = int(candidate["units"])
        except (ValueError, TypeError) as exc:
            raise ValidationError("Units must be an integer.") from exc
        if units not in range(1, 7):
            raise ValidationError("Units must be from 1 to 6.")
        row.update(title=title, instructor=instructor, units=units)
        self.stores["subjects"].save(subjects)
        return row

    def delete_subject(self, code):
        subjects = self.read("subjects")
        row = find_one(subjects, "code", code, "Subject")
        if any(e["subject_code"] == row["code"] for e in self.read("enrollments")):
            raise ValidationError("Cannot delete a subject referenced by an enrollment.")
        self.stores["subjects"].save([s for s in subjects if s is not row])

    def search_subjects(self, term):
        term = term.strip().lower()
        return [s for s in self.read("subjects") if any(term in str(s[field]).lower()
                for field in ("code", "title", "instructor"))]

    # Enrollments
    def enroll(self, student_id, subject_code, semester, school_year):
        students = self.read("students")
        student = find_one(students, "student_id", student_id, "Student")
        if student["status"] != "Active":
            raise ValidationError("Only active students may enroll.")
        subject = find_one(self.read("subjects"), "code", subject_code, "Subject")
        if semester not in ("1st Semester", "2nd Semester", "Summer"):
            raise ValidationError("Select a valid semester.")
        year_match = re.fullmatch(r"(\d{4})-(\d{4})", school_year.strip())
        if not year_match or int(year_match.group(2)) != int(year_match.group(1)) + 1:
            raise ValidationError("School year format must be YYYY-YYYY, e.g. 2026-2027.")
        enrollments = self.read("enrollments")
        if any(e["student_id"] == student["student_id"] and e["subject_code"] == subject["code"]
               and e["semester"] == semester and e["school_year"] == school_year.strip()
               for e in enrollments):
            raise ValidationError("Student is already enrolled in this subject for that term.")
        enrollment = {"enrollment_id": next_id(enrollments, "enrollment_id", "ENR"),
                      "student_id": student["student_id"], "subject_code": subject["code"],
                      "semester": semester, "school_year": school_year.strip(),
                      "enrolled_at": current_timestamp()}
        self.stores["enrollments"].append(enrollment)
        return enrollment

    def withdraw(self, enrollment_id):
        enrollments = self.read("enrollments")
        row = find_one(enrollments, "enrollment_id", enrollment_id, "Enrollment")
        if any(g["enrollment_id"] == row["enrollment_id"] for g in self.read("grades")):
            raise ValidationError("This enrollment has a grade. An admin must remove the grade first.")
        self.stores["enrollments"].save([e for e in enrollments if e is not row])

    def list_enrollments(self, term=""):
        term = term.strip().lower()
        students = {s["student_id"]: s["full_name"] for s in self.read("students")}
        subjects = {s["code"]: s["title"] for s in self.read("subjects")}
        entries = []
        for row in self.read("enrollments"):
            entry = {**row, "student_name": students.get(row["student_id"], "[Missing student]"),
                     "subject_title": subjects.get(row["subject_code"], "[Missing subject]")}
            if any(term in str(entry.get(k, "")).lower() for k in (
                    "enrollment_id", "student_id", "student_name", "subject_code",
                    "subject_title", "semester", "school_year")):
                entries.append(entry)
        return entries

    # Grades: percentage grades, weighted 30 / 30 / 40
    def save_grade(self, enrollment_id, prelim, midterm, final_exam):
        enrollment = find_one(self.read("enrollments"), "enrollment_id", enrollment_id, "Enrollment")
        values = []
        for label, raw in (("Prelim", prelim), ("Midterm", midterm), ("Final", final_exam)):
            try:
                number = float(raw)
            except (ValueError, TypeError) as exc:
                raise ValidationError(f"{label} grade must be numeric (0-100).") from exc
            if not 0 <= number <= 100 or number != number:
                raise ValidationError(f"{label} grade must be between 0 and 100.")
            values.append(round(number, 2))
        average = round(values[0] * 0.30 + values[1] * 0.30 + values[2] * 0.40 + 0.000001, 2)
        grades = self.read("grades")
        existing = next((g for g in grades if g["enrollment_id"] == enrollment["enrollment_id"]), None)
        record = {"enrollment_id": enrollment["enrollment_id"],
                  "prelim": values[0], "midterm": values[1], "final_exam": values[2],
                  "average": average, "remarks": "Passed" if average >= 75 else "Failed",
                  "updated_at": current_timestamp()}
        if existing:
            existing.update(record)
            self.stores["grades"].save(grades)
        else:
            self.stores["grades"].append(record)
        return record

    def delete_grade(self, enrollment_id):
        grades = self.read("grades")
        row = find_one(grades, "enrollment_id", enrollment_id, "Grade")
        self.stores["grades"].save([g for g in grades if g is not row])

    def list_grades(self, term=""):
        term = term.strip().lower()
        enrollments = {e["enrollment_id"]: e for e in self.list_enrollments()}
        entries = []
        for grade in self.read("grades"):
            e = enrollments.get(grade["enrollment_id"], {})
            entry = {**grade, "student_id": e.get("student_id", "?"),
                     "student_name": e.get("student_name", "?"),
                     "subject_code": e.get("subject_code", "?"),
                     "semester": e.get("semester", "?"), "school_year": e.get("school_year", "?")}
            if any(term in str(entry.get(k, "")).lower() for k in (
                    "enrollment_id", "student_id", "student_name", "subject_code", "remarks")):
                entries.append(entry)
        return entries

    # Reports
    def population_report(self):
        students = self.read("students")
        programs = Counter(row["program"] for row in students)
        years = Counter(str(row["year_level"]) for row in students)
        statuses = Counter(row["status"] for row in students)
        lines = ["STUDENT POPULATION REPORT", f"Generated: {current_timestamp()}",
                 "=" * 56, f"Total students: {len(students)}", "", "BY PROGRAM"]
        lines += [f"  {name:<25} {count:>5}" for name, count in sorted(programs.items())] or ["  No students"]
        lines += ["", "BY YEAR LEVEL"]
        lines += [f"  Year {name:<20} {count:>5}" for name, count in sorted(years.items())] or ["  No students"]
        lines += ["", "BY STATUS"]
        lines += [f"  {name:<25} {count:>5}" for name, count in sorted(statuses.items())] or ["  No students"]
        return "\n".join(lines) + "\n"

    def performance_report(self):
        grades = self.list_grades()
        subjects = {s["code"]: s["title"] for s in self.read("subjects")}
        grouped = {}
        for grade in grades:
            grouped.setdefault(grade["subject_code"], []).append(grade)
        lines = ["SUBJECT GRADE PERFORMANCE REPORT", f"Generated: {current_timestamp()}",
                 "=" * 84, f"Graded enrollments: {len(grades)}", "",
                 f"{'CODE':<12} {'SUBJECT':<29} {'COUNT':>6} {'AVG':>8} {'PASS':>6} {'FAIL':>6}",
                 "-" * 84]
        for code, group in sorted(grouped.items()):
            avg = sum(g["average"] for g in group) / len(group)
            passed = sum(g["remarks"] == "Passed" for g in group)
            lines.append(f"{code:<12} {subjects.get(code, '?')[:29]:<29} {len(group):>6} "
                         f"{avg:>8.2f} {passed:>6} {len(group) - passed:>6}")
        if not grouped:
            lines.append("No grades recorded yet.")
        passed_all = sum(g["remarks"] == "Passed" for g in grades)
        lines += ["-" * 84, f"Overall passing rate: {(passed_all / len(grades) * 100) if grades else 0:.1f}%"]
        return "\n".join(lines) + "\n"

    def student_report_card(self, student_id):
        student = find_one(self.read("students"), "student_id", student_id, "Student")
        enrollments = [e for e in self.list_enrollments() if e["student_id"] == student["student_id"]]
        grades = {g["enrollment_id"]: g for g in self.read("grades")}
        lines = ["STUDENT REPORT CARD", f"Generated: {current_timestamp()}", "=" * 84,
                 f"ID: {student['student_id']}     Name: {student['full_name']}",
                 f"Program: {student['program']}     Year: {student['year_level']}     Status: {student['status']}",
                 "", f"{'TERM':<20} {'SUBJECT':<12} {'PRE':>7} {'MID':>7} {'FIN':>7} {'AVG':>7} {'REMARKS':<10}",
                 "-" * 84]
        averages = []
        for e in enrollments:
            g = grades.get(e["enrollment_id"])
            if g:
                averages.append(g["average"])
                values = [f"{g[k]:.1f}" for k in ("prelim", "midterm", "final_exam", "average")]
                remarks = g["remarks"]
            else:
                values = ["--"] * 4
                remarks = "Pending"
            term = f"{e['school_year']} {e['semester'].split()[0]}"
            lines.append(f"{term:<20} {e['subject_code']:<12} " + " ".join(f"{v:>7}" for v in values)
                         + f" {remarks:<10}")
        if not enrollments:
            lines.append("No enrollments found.")
        lines += ["-" * 84, f"Average of recorded subject grades: "
                  f"{(sum(averages) / len(averages)):.2f}" if averages else
                  "Average of recorded subject grades: N/A"]
        return "\n".join(lines) + "\n"

    def export_report(self, name, content):
        safe_name = re.sub(r"[^a-z0-9_-]", "_", name.lower())[:40]
        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        path = self.report_dir / filename
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as exc:
            raise StorageError(f"Could not export report: {exc}") from exc
        return path
