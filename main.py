from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests

app = FastAPI()

@app.get("/terms", response_class=HTMLResponse)
def terms():
    return """
    <html>
      <head><title>Terms of Service</title></head>
      <body>
        <h1>Terms of Service</h1>
        <p>Estos son los términos de uso de BorealisDrop.</p>
        <p>El usuario acepta utilizar la plataforma de manera responsable y conforme a la ley.</p>
      </body>
    </html>
    """

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return """
    <html>
      <head><title>Privacy Policy</title></head>
      <body>
        <h1>Privacy Policy</h1>
        <p>Esta es la política de privacidad de BorealisDrop.</p>
        <p>No compartimos información personal con terceros sin consentimiento.</p>
      </body>
    </html>
    """

@app.get("/oauth/callback")
def oauth_callback(code: str):
    url = "https://open-api.tiktokglobalshop.com/oauth/access_token/"
    payload = {
        "client_key": "aw07ofuldk0fj851",
        "client_secret": "TARdEelCWjyNSNdf36SukCA7d4EBlowO",
        "code": code,
        "grant_type": "authorization_code"
    }
    r = requests.post(url, data=payload)
    return r.json()
