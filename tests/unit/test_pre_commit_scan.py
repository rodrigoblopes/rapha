"""The commit guard has to be tested, or it is just a comment that runs.

Every credential below is invented, which is why this file needs the opt-out:
pre-commit-scan: fixtures-are-invented
"""

from pre_commit_scan import check_content, check_path


class TestFilesThatAreDataNotCode:
    def test_a_database_is_blocked(self):
        assert check_path("rapha.db") is not None

    def test_course_material_is_blocked(self):
        assert check_path("Treino Intermediario 01.pdf") is not None
        assert check_path("modulo17.mp4") is not None

    def test_anything_under_protocol_is_blocked(self):
        assert check_path("protocol/fichas.json") is not None
        assert check_path("data/rapha.db") is not None

    def test_but_the_parser_package_of_the_same_name_is_not(self):
        # src/rapha/protocol/ is the code that reads the course; protocol/ at the
        # root would be the course itself. Blocking the former blocks the repo.
        assert check_path("src/rapha/protocol/ficha_pdf.py") is None
        assert check_path("src/rapha/protocol/models.py") is None

    def test_a_token_store_is_blocked(self):
        assert check_path("garmin_tokens.json") is not None

    def test_a_body_photo_is_blocked(self):
        assert check_path("front.jpg") is not None


class TestFilesNamedLikeCredentials:
    """Learned the hard way: a real password file arrived as `pwd.txt.txt`.

    It had no `key = value` to match, so the content scanner sailed straight past
    it. Content matching alone was never going to be enough — a file whose *name*
    says credential is blocked regardless of what is inside it.
    """

    def test_the_file_that_actually_got_through(self):
        assert check_path("pwd.txt.txt") is not None

    def test_other_credential_names(self):
        assert check_path("password.txt") is not None
        assert check_path("passwd") is not None
        assert check_path("my-secrets.yaml") is not None
        assert check_path("credentials.json") is not None

    def test_key_material(self):
        assert check_path("server.pem") is not None
        assert check_path("id_rsa") is not None


class TestCodeMustStillCommit:
    def test_source_passes(self):
        assert check_path("src/rapha/units.py") is None

    def test_the_env_contract_passes(self):
        assert check_path(".env.example") is None

    def test_docs_pass(self):
        assert check_path("CLAUDE.md") is None
        assert check_path("DECISIONS.md") is None


class TestContentScanning:
    def test_an_underscored_credential_name_is_caught(self):
        # \bpassword\b does NOT match GARMIN_PASSWORD — underscore is a word char.
        found = check_content("x.py", b"GARMIN_PASSWORD = hunter2supersecret")
        assert found

    def test_a_private_key_is_caught(self):
        found = check_content("x.pem", b"-----BEGIN RSA PRIVATE KEY-----\nAAAA")
        assert found

    def test_prose_about_passwords_is_not_a_credential(self):
        found = check_content("README.md", b"Stores OAuth tokens, never a password.")
        assert not found

    def test_ordinary_config_is_not_a_credential(self):
        found = check_content("cfg.env", b"DEFICIT_BPS=1750\nPORTAL_PORT=8766")
        assert not found

    def test_code_that_merely_handles_a_password_is_not_a_leak(self):
        """The guard must not fire on the very code that avoids storing passwords.

        A rule that flags ordinary source gets switched off, and then it protects
        nothing at all.
        """
        assert not check_content("cli.py", b"password = sys.stdin.read().strip()")
        assert not check_content("cli.py", b"password = getpass.getpass(prompt)")
        assert not check_content("auth.py", b"def mint(cfg, password: str) -> str:")

    def test_passing_a_variable_through_is_not_a_leak(self):
        # `password=password,` inside a call is a variable name, not a credential.
        assert not check_content("auth.py", b"    Garmin(\n        password=password,\n    )")

    def test_but_a_real_looking_value_still_trips_it(self):
        assert check_content("x.py", b"PASSWORD = correcthorse7battery")

    def test_a_quoted_literal_credential_is_still_caught(self):
        assert check_content("x.py", b'api_key = "abcd1234efgh5678"')

    def test_binary_content_does_not_explode(self):
        assert check_content("x.bin", b"\xff\xfe\x00\x01") == []


class TestTheFixtureOptOut:
    """A test proving the guard works must contain credential-shaped strings."""

    PRAGMA = b"# pre-commit-scan: fixtures-are-invented"
    LEAK = b"\nGARMIN_PASSWORD = hunter2supersecret"

    def test_a_test_file_may_opt_out_of_content_scanning(self):
        assert check_content("tests/unit/test_x.py", self.PRAGMA + self.LEAK) == []

    def test_the_opt_out_does_not_work_outside_tests(self):
        # Otherwise the pragma becomes a way to smuggle a real secret into src/.
        assert check_content("src/rapha/x.py", self.PRAGMA + self.LEAK)

    def test_the_opt_out_does_not_disable_path_rules(self):
        assert check_path("tests/fixtures/garmin_tokens.json") is not None
