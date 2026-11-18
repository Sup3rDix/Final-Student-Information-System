"""Run: python -m unittest discover -s tests -v"""

import json
import tempfile
import unittest
from pathlib import Path

from sis.database import StorageError
from sis.service import StudentSystem, ValidationError


class StudentSystemTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data_path = Path(self.directory.name) / "data"
        self.sys = StudentSystem(self.data_path)

    def tearDown(self):
        self.directory.cleanup()

    def seed(self):
        student = self.sys.add_student("Sample Learner", "BSIT", 2, "learner@example.edu")
        subject = self.sys.add_subject("IT210", "Programming II", 3, "Dr. Teacher")
        enrollment = self.sys.enroll(student["student_id"], subject["code"],
                                     "1st Semester", "2026-2027")
        return student, subject, enrollment

    def test_empty_files_created(self):
        for name in ("students", "subjects", "enrollments", "grades", "users", "settings"):
            self.assertTrue((self.data_path / f"{name}.txt").is_file())
            self.assertEqual(self.sys.read(name), [])

    def test_authentication_salted_and_roles(self):
        self.sys.create_initial_admin("teacher", "Secur3Pass!")
        self.sys.create_user("assistant", "StaffPass123", "Staff")
        rows = self.sys.read("users")
        self.assertEqual([r["role"] for r in rows], ["Administrator", "Staff"])
        self.assertNotIn("Secur3Pass!", (self.data_path / "users.txt").read_text())
        self.assertNotEqual(rows[0]["salt"], rows[1]["salt"])
        self.assertEqual(self.sys.authenticate("teacher", "Secur3Pass!")["role"], "Administrator")
        self.assertEqual(self.sys.authenticate("assistant", "StaffPass123")["role"], "Staff")
        self.assertIsNone(self.sys.authenticate("assistant", "wrongpass"))
        self.sys.set_user_active("assistant", False, "teacher")
        self.assertIsNone(self.sys.authenticate("assistant", "StaffPass123"))
        self.sys.change_password("teacher", "Secur3Pass!", "NewPass12345")
        self.assertIsNone(self.sys.authenticate("teacher", "Secur3Pass!"))
        self.assertIsNotNone(self.sys.authenticate("teacher", "NewPass12345"))

    def test_relational_records_and_persistence(self):
        student, subject, enrollment = self.seed()
        grade = self.sys.save_grade(enrollment["enrollment_id"], 90, 80, 100)
        self.assertEqual(grade["average"], 91.0)
        self.assertEqual(grade["remarks"], "Passed")
        self.assertEqual(self.sys.list_enrollments()[0]["student_name"], "Sample Learner")
        self.assertEqual(self.sys.list_grades()[0]["subject_code"], "IT210")
        self.assertEqual(len(StudentSystem(self.data_path).read("students")), 1)
        self.assertEqual(len(StudentSystem(self.data_path).read("grades")), 1)
        self.assertIn("Sample Learner", self.sys.student_report_card(student["student_id"]))

    def test_validation_and_reference_protection(self):
        student, subject, enrollment = self.seed()
        with self.assertRaises(ValidationError):
            self.sys.enroll(student["student_id"], subject["code"], "1st Semester", "2026-2027")
        with self.assertRaises(ValidationError):
            self.sys.delete_student(student["student_id"])
        with self.assertRaises(ValidationError):
            self.sys.delete_subject(subject["code"])
        with self.assertRaises(ValidationError):
            self.sys.add_student("Bad", "BSIT", 0, "bad@example.edu")
        with self.assertRaises(ValidationError):
            self.sys.save_grade(enrollment["enrollment_id"], 110, 85, 90)
        self.sys.save_grade(enrollment["enrollment_id"], 70, 70, 80)
        with self.assertRaises(ValidationError):
            self.sys.withdraw(enrollment["enrollment_id"])
        self.sys.delete_grade(enrollment["enrollment_id"])
        self.sys.withdraw(enrollment["enrollment_id"])
        self.sys.delete_subject(subject["code"])
        self.sys.delete_student(student["student_id"])
        self.assertEqual(len(self.sys.read("enrollments")), 0)

    def test_updates_rewrite_and_search(self):
        student, subject, enrollment = self.seed()
        self.sys.update_student(student["student_id"], full_name="Updated Learner", year_level=3)
        self.sys.update_subject(subject["code"], title="Advanced Programming")
        self.assertEqual(self.sys.search_students("updated")[0]["year_level"], 3)
        self.assertEqual(self.sys.search_subjects("advanced")[0]["code"], subject["code"])
        self.assertEqual(len(self.sys.list_enrollments("Updated Learner")), 1)

    def test_reports_export_and_theme_persist(self):
        self.seed()
        self.sys.set_theme("Amber Vintage")
        self.assertEqual(StudentSystem(self.data_path).theme(), "Amber Vintage")
        body = self.sys.population_report()
        self.assertIn("Total students: 1", body)
        self.assertIn("SUBJECT GRADE PERFORMANCE", self.sys.performance_report())
        report = self.sys.export_report("population", body)
        self.assertEqual(report.read_text(encoding="utf-8"), body)

    def test_six_themes_persist_and_invalid_theme_rejected(self):
        from sis.terminal import PALETTES
        self.assertEqual(len(PALETTES), 6)
        for name in PALETTES:
            self.sys.set_theme(name)
            self.assertEqual(StudentSystem(self.data_path).theme(), name)
        with self.assertRaises(ValidationError):
            self.sys.set_theme("Made Up Theme")

    def test_dashboard_metrics_use_real_records(self):
        from sis.app import App
        student, subject, enrollment = self.seed()
        app = App(self.data_path)
        metrics = app.dashboard_metrics()
        self.assertEqual(metrics["students"], 1)
        self.assertEqual(metrics["active"], 1)
        self.assertEqual(metrics["subjects"], 1)
        self.assertEqual(metrics["enrollments"], 1)
        self.assertEqual(metrics["graded"], 0)
        self.sys.save_grade(enrollment["enrollment_id"], 80, 85, 90)
        self.assertEqual(app.dashboard_metrics()["passing"], 1)

    def test_terminal_narrow_display_and_no_color(self):
        from io import StringIO
        from unittest.mock import patch
        from contextlib import redirect_stdout
        from sis.terminal import Terminal
        ui = Terminal("Midnight Gold")
        ui.color_enabled = False
        rows = [["STU0001", "Very Long Sample Learner", "BSIT", "3", "Active"]]
        with patch("sis.terminal.shutil.get_terminal_size", return_value=__import__('os').terminal_size((70, 25))):
            out = StringIO()
            with redirect_stdout(out):
                ui.table(["ID", "NAME", "PROGRAM", "YEAR", "STATUS"], rows,
                         [12, 26, 14, 5, 10])
            self.assertNotIn("\033[", out.getvalue())
            self.assertIn("STU0001", out.getvalue())
            self.assertIn("1 record(s) shown", out.getvalue())

    def test_corrupted_text_prevents_overwrite(self):
        path = self.data_path / "students.txt"
        path.write_text("{not valid json}\n", encoding="utf-8")
        with self.assertRaises(StorageError):
            self.sys.add_student("Test Name", "BSIT", 2, "test@example.edu")
        self.assertEqual(path.read_text(encoding="utf-8"), "{not valid json}\n")

    def test_structurally_invalid_record_handled(self):
        path = self.data_path / "subjects.txt"
        path.write_text('{"code":"IT99"}\n', encoding="utf-8")
        with self.assertRaises(StorageError):
            self.sys.read("subjects")

    def test_sample_jsonl_format(self):
        self.sys.add_subject("GE110", "Test Course", 3, "Dr. Faculty")
        with (self.data_path / "subjects.txt").open(encoding="utf-8") as handle:
            self.assertEqual(json.loads(handle.readline())["code"], "GE110")


class TerminalUpgradeTests(unittest.TestCase):
    def test_windows_password_mask_reader_mock(self):
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch
        from sis.password_input import read_masked

        class FakeInput:
            def isatty(self):
                return True

        class FakeOutput(StringIO):
            def isatty(self):
                return True

        keys = iter(['P', 'a', 's', 'X', '\b', 's', '1', '2', '3', '\r'])
        fake_msvcrt = SimpleNamespace(getwch=lambda: next(keys))
        output = FakeOutput()
        with patch('sis.password_input.os', SimpleNamespace(name='nt')), \
                patch.dict(__import__('sys').modules, {'msvcrt': fake_msvcrt}), \
                patch('sys.stdin', FakeInput()), patch('sys.stdout', output):
            result = read_masked('Password: ')
        self.assertEqual(result, 'Pass123')
        self.assertEqual(output.getvalue().count('*'), 8)
        self.assertNotIn('Pass123', output.getvalue())

    def test_wide_terminal_centered_with_wider_layout(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from sis.terminal import Terminal
        ui = Terminal("Midnight Gold")
        ui.color_enabled = False
        with patch("sis.terminal.shutil.get_terminal_size", return_value=__import__('os').terminal_size((160, 48))):
            self.assertEqual(ui.width(), 132)
            self.assertEqual(ui.margin(), 14)
            stream = StringIO()
            with redirect_stdout(stream):
                ui.screen("Center check")
                ui.login_panel()
            lines = stream.getvalue().splitlines()
            self.assertTrue(all(line.startswith(" " * 14) for line in lines if line.strip()))
            self.assertIn("CENTER CHECK", stream.getvalue())
            self.assertIn("Passwords display as *", stream.getvalue())

    @unittest.skipIf(__import__('os').name == 'nt', 'Unix TTY mock')
    def test_password_masking_handles_backspace_without_echoing_real_secret(self):
        from io import StringIO
        from unittest.mock import patch
        from sis.password_input import read_masked

        class FakeInput:
            def __init__(self, chars):
                self.chars = iter(chars)
            def isatty(self):
                return True
            def fileno(self):
                return 0
            def read(self, _):
                return next(self.chars)

        class FakeOutput(StringIO):
            def isatty(self):
                return True

        output = FakeOutput()
        with patch('sys.stdin', FakeInput('AbcX\x7f2\r')), patch('sys.stdout', output), \
                patch('termios.tcgetattr', return_value=[]), \
                patch('termios.tcsetattr'), patch('tty.setraw'):
            password = read_masked('Enter password: ')
        self.assertEqual(password, 'Abc2')
        shown = output.getvalue()
        self.assertIn('Enter password: ****\b \b*\n', shown)
        self.assertNotIn('Abc2', shown)


class AdminEntryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.sys = StudentSystem(self.root / "data")

    def tearDown(self):
        self.directory.cleanup()

    def test_new_installation_students_start_empty_and_admin_can_add(self):
        from sis.app import App
        app = App(self.root / "data")
        self.assertEqual(app.dashboard_metrics()["students"], 0)
        self.assertEqual(app.dashboard_metrics()["enrollments"], 0)
        self.assertEqual(app.dashboard_metrics()["graded"], 0)
        app.current_user = {"username": "admin", "role": "Administrator"}
        from unittest.mock import patch
        with patch.object(app.ui, "ask", side_effect=["Test Student", "BSIT", "1", "test@example.edu"]), \
             patch.object(app.ui, "success"):
            app.add_student()
        self.assertEqual(app.dashboard_metrics()["students"], 1)
        self.assertEqual(StudentSystem(self.root / "data").read("students")[0]["student_id"], "STU0001")

    def test_staff_cannot_change_students_or_select_edit_options(self):
        from unittest.mock import patch
        from sis.app import App
        app = App(self.root / "data")
        app.current_user = {"username": "staff", "role": "Staff"}
        with patch.object(app.ui, "screen"), patch.object(app.ui, "menu", return_value="0") as menu:
            app.students_menu()
        choices = dict(menu.call_args.args[1])
        self.assertEqual(set(choices), {"1", "3"})
        for action in (app.add_student, app.edit_student, app.delete_student):
            with self.assertRaisesRegex(ValidationError, "Administrator access required"):
                action()
        app.current_user = {"username": "admin", "role": "Administrator"}
        with patch.object(app.ui, "screen"), patch.object(app.ui, "menu", return_value="0") as menu:
            app.students_menu()
        self.assertEqual(set(dict(menu.call_args.args[1])), {"1", "2", "3", "4", "5"})

    def test_bundle_records_are_empty_but_subject_samples_exist(self):
        packaged = Path(__file__).resolve().parents[1] / "data"
        for name in ("students", "enrollments", "grades", "users"):
            self.assertEqual((packaged / f"{name}.txt").read_text(encoding="utf-8"), "")
        self.assertGreaterEqual(len(StudentSystem(packaged).read("subjects")), 1)


if __name__ == "__main__":
    unittest.main()
