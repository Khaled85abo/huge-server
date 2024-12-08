import os
from fastapi import BackgroundTasks
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from jinja2 import Environment, FileSystemLoader, select_autoescape


# Set up Jinja2 environment
env = Environment(
    loader=FileSystemLoader(['./app/templates']),
    autoescape=select_autoescape(['html', 'xml'])
)

# class Envs:
#     MAIL_USERNAME = os.getenv('MAIL_USERNAME')
#     MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
#     MAIL_FROM = os.getenv('MAIL_FROM')
#     MAIL_PORT = int(os.getenv('MAIL_PORT'))
#     MAIL_SERVER = os.getenv('MAIL_SERVER')
#     MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME')
class Envs:
    MAIL_USERNAME = "test@test.com"
    MAIL_PASSWORD = "test"
    MAIL_FROM = "test@test.com"
    MAIL_PORT =     587
    MAIL_SERVER = ""
    MAIL_FROM_NAME = ""


conf = ConnectionConfig(
    MAIL_USERNAME=Envs.MAIL_USERNAME,
    MAIL_PASSWORD=Envs.MAIL_PASSWORD,
    MAIL_FROM=Envs.MAIL_FROM,
    MAIL_PORT=Envs.MAIL_PORT,
    MAIL_SERVER=Envs.MAIL_SERVER,
    MAIL_FROM_NAME=Envs.MAIL_FROM_NAME,
    MAIL_STARTTLS=True,  # Replace MAIL_TLS with this if your service requires STARTTLS
    MAIL_SSL_TLS=False,  # Replace MAIL_SSL with this if your service does not use SSL/TLS directly
    USE_CREDENTIALS=True,
    TEMPLATE_FOLDER='./app/templates'
)


async def send_verification_email(subject: str, email_to: str, body: dict):
    template = env.get_template('verify_account.html')
    email_body = template.render(body)
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        body=email_body,
        subtype='html',
    )
    fm = FastMail(conf)
    await fm.send_message(message, template_name='verify_account.html')

async def send_email_async(subject: str, email_to: str, body: dict):
    template = env.get_template('verify_account.html')
    email_body = template.render(body)
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        body=email_body,
        subtype='html',
    )

    fm = FastMail(conf)
    await fm.send_message(message, template_name='verify_account.html')

def send_email_background(background_tasks: BackgroundTasks, subject: str, email_to: str, body: dict):
    template = env.get_template('verify_account.html')
    email_body = template.render(body)
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        body=email_body,
        subtype='html',
    )
    fm = FastMail(conf)
    background_tasks.add_task(
       fm.send_message, message, template_name='verify_account.html')