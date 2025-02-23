
import os
import random
import string
import boto3
from fastapi import HTTPException
from app.baseController import ControllerBase
from app.user.userDTO import UserInsert, UserSoftDelete, UserUpdateUser
from botocore.exceptions import BotoCoreError, NoCredentialsError

from models.models import Users

class ServiceUser(ControllerBase[Users, UserInsert, UserUpdateUser, UserSoftDelete]): 
    ...

userServices = ServiceUser(Users)

ses_client = boto3.client(
    'ses',
    aws_access_key_id= os.getenv("AWS_KEY"),
    aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
    region_name="us-east-2"
)

CONFIGURATION_SET = "konempleo-config-set"

def generate_temp_password(length=10):
    """Generates a random alphanumeric password."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def send_email_with_temp_password(email: str, temp_password: str):
    """Sends an email using AWS SES with the temporary password."""
    
    # AWS SES Configuration
    SENDER = "mail@konempleo.ai"  # Change to your verified SES sender email
    CHARSET = "UTF-8"
    SUBJECT = "Bienvenido a KonEmpleo - Su acceso temporal"

    BODY_TEXT = f"""
    ¡Bienvenido a KonEmpleo!
    
    Estimado/a,

    Nos complace darle la bienvenida a KonEmpleo.

    Para comenzar, hemos generado una contraseña temporal para usted:
    
    Contraseña Temporal: {temp_password}
    
    Haga clic en el siguiente enlace para acceder a su cuenta y actualizar su contraseña:
    
    https://konempleo.ai/login
    
    Atentamente,
    El equipo de KonEmpleo
    """

    BODY_HTML = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Bienvenido a KonEmpleo</title>
    </head>
    <body>
        <table width="100%" style="background-color: #ffffff; max-width: 600px; margin: auto;">
            <tr>
                <td style="text-align: center; padding: 20px;">
                    <img src="https://konempleo.ai/_nuxt/ke_logo_dark.D8QroFYK.png" alt="KonEmpleo Logo" style="max-width: 20%; height: auto;">
                </td>
            </tr>
            <tr>
                <td style="text-align: center; padding: 20px; background-color: #002E5D; color: #ffffff; font-size: 24px; font-weight: bold;">
                    ¡Bienvenido a KonEmpleo!
                </td>
            </tr>
            <tr>
                <td style="padding: 20px; font-size: 16px; color: #333333;">
                    <p>Estimado/a,</p>
                    <p>Nos complace darle la bienvenida a KonEmpleo.</p>
                    <p>Para comenzar, hemos generado una contraseña temporal para usted:</p>
                    <p style="text-align: center; font-weight: bold; font-size: 18px;">{temp_password}</p>
                    <p>Haga clic en el botón a continuación para acceder a su cuenta y actualizar su contraseña:</p>
                    <p style="text-align: center;">
                        <a href="https://konempleo.ai/login" style="background-color: #002E5D; color: #ffffff; padding: 12px 24px; text-decoration: none; font-size: 16px; border-radius: 5px;">Actualizar Contraseña</a>
                    </p>
                </td>
            </tr>
            <tr>
                <td style="text-align: center; padding: 20px; background-color: #002E5D; color: #ffffff; font-size: 14px;">
                    &copy; 2025 KonEmpleo. Todos los derechos reservados.
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    try:
    

        # Send the email
        response = ses_client.send_email(
            Destination={"ToAddresses": [email]},
            Message={
                "Body": {
                    "Html": {
                        "Charset": CHARSET,
                        "Data": BODY_HTML,
                    },
                    "Text": {
                        "Charset": CHARSET,
                        "Data": BODY_TEXT,
                    },
                },
                "Subject": {
                    "Charset": CHARSET,
                    "Data": SUBJECT,
                },
            },
            Source=SENDER,
            ConfigurationSetName="konempleo-config-set"
        )

        print(f"Email sent successfully to {email}. Message ID: {response['MessageId']}")

    except (BotoCoreError, NoCredentialsError) as e:
        print(f"Failed to send email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send email. Please try again later.")
