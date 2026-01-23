#!/usr/bin/env python3
"""
Lifeline Home Buyers - Public Site
Clean standalone version for Railway deployment.
"""
import os
import sys
from pathlib import Path

# Setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "public_site" / "templates"

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lifeline Home Buyers")

# Setup templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/health")
async def health():
    return {"status": "ok", "templates": str(TEMPLATES_DIR), "exists": TEMPLATES_DIR.exists()}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    stats = {'total_properties': 0, 'probate': 0, 'tax_delinquent': 0}
    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats": stats,
        "page_title": "Lifeline Home Buyers | We Buy Houses Ohio",
        "meta_description": "We buy houses in any condition - cash offers in 24 hours."
    })

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {
        "request": request,
        "page_title": "About | Lifeline Home Buyers",
        "meta_description": "Our story - why we started Lifeline Home Buyers."
    })

@app.get("/get-offer", response_class=HTMLResponse)
async def get_offer(request: Request):
    return templates.TemplateResponse("get_offer.html", {
        "request": request,
        "page_title": "Get Cash Offer | Lifeline Home Buyers",
        "meta_description": "Get a free cash offer for your property."
    })

@app.get("/probate", response_class=HTMLResponse)
async def probate(request: Request):
    return templates.TemplateResponse("probate.html", {
        "request": request,
        "properties": [],
        "page_title": "Probate Properties | Lifeline Home Buyers",
        "meta_description": "We help with inherited and probate properties."
    })

@app.get("/tax-delinquent", response_class=HTMLResponse)
async def tax_delinquent(request: Request):
    return templates.TemplateResponse("tax_delinquent.html", {
        "request": request,
        "properties": [],
        "page_title": "Tax Delinquent Help | Lifeline Home Buyers",
        "meta_description": "Behind on taxes? We can help."
    })

@app.get("/calculator", response_class=HTMLResponse)
async def calculator(request: Request):
    return templates.TemplateResponse("offer_calculator.html", {
        "request": request,
        "page_title": "Cash Offer Calculator | Lifeline Home Buyers",
        "meta_description": "Calculate your cash offer."
    })

@app.get("/thank-you", response_class=HTMLResponse)
async def thank_you(request: Request):
    return templates.TemplateResponse("thank_you.html", {
        "request": request,
        "page_title": "Thank You | Lifeline Home Buyers",
        "meta_description": "We'll contact you soon."
    })

@app.post("/submit-lead")
async def submit_lead(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(None),
    property_address: str = Form(...),
    message: str = Form(None),
    source_page: str = Form(None)
):
    logger.info(f"Lead received: {name} - {phone} - {property_address}")
    # TODO: Save to database
    return RedirectResponse(url="/thank-you", status_code=303)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting on port {port}")
    logger.info(f"Templates: {TEMPLATES_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=port)
