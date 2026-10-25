"""Helpers shared by the dashboard tests: recruiter accounts and the real login."""
from sazon import accounts

PASSWORD = "contraseña-segura-1"


def seed_accounts(path, *names):
    for name in names or ("Ana", "Luis"):
        accounts.add_account(path, name, PASSWORD)


def login(at, name="Ana", password=PASSWORD):
    at.text_input(key="login_name").set_value(name)
    at.text_input(key="login_password").set_value(password)
    at.form_submit_button(key="login_submit").click().run()
    return at


def logout(at):
    at.sidebar.button(key="logout").click().run()
    return at
